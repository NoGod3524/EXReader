# 应用模块公开边界故障与模糊回归（J23）

独立测试包，只消费安装后的公开包，不重写 SDK 或产品模块的 fuzz，也不改动共享实现。
源码在 `tests/reader_app_boundary_fuzz/`，工作流为
`.github/workflows/reader-app-boundary-fuzz.yml`，证据在
`docs/validation/reader-app-boundary-fuzz.json`。本文件说明契约与出口；
**验收状态见末节，未通过云端实测前 `accepted=false`。**

固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`；冻结 SDK
`9854061be331fe603a1822d9b2b36ee357154927`（3.40.0 / ABI 1）；产品
schema1、既有 wire v1 与 reading anchor v1/v2 逐字不改；不新增同步实体、不写 SDK
私有 SQL、不加常驻服务或插件框架。

## 目标

在独立消费者上，对四个应用边界做**有界、确定性、可重放**的分配与故障回归：

1. 设置文件：`reader_preferences_load` / `save` / `validate` / `import_legacy`（`EXReaderPreferences 0.1.0`）。
2. 阅读 wire 校验与保留：`reader_revision_validate` / `receive` / `local` / `get` / `outbox` / `retry` / `ack` / `heads`（`EXReaderRevisions 0.3.0`）。
3. reading-state 编解码：`reader_rs_decode` / `reader_rs_encode` / `reader_rs_encode_v2`（`EXReaderReadingState 0.1.0`）。
4. 公开字符串与错误边界：状态名、错误消息长度、NUL 终止、空路径、Unicode 路径、超限输入。

只接受**真实合法种子**（先由公开 API 验证通过）的变异；不把“进程非零退出”当作通过，
也不把“成功生成报告”当作功能通过。

## 公开接口、所有权与线程

| 接口 | 输入 | 输出/内存归属 | 失败语义 |
| --- | --- | --- | --- |
| `reader_preferences_load(path, inout, options, error)` | 借用 UTF-8 路径与选项 | 只整体替换 `*inout` | 任何失败（含取消、未知版本、超限）后 `*inout` 与磁盘文件逐字节不变 |
| `reader_preferences_save(preferences, path, options, error)` | 借用记录与路径 | 无返回对象 | 先校验；失败不写文件；同目录临时文件 + 原子替换 |
| `reader_revision_validate(store, bytes, count, expected, info, error)` | 借用字节与期望 SHA | `info` 为调用者所有；失败时全部置零 | 只读，不写产品库、不入队 |
| `reader_revision_receive(store, ...)` | 同上；远程 SHA 必填 | `info` 借用期外无效 | 成功才在一个事务内保存修订 + outbox 行；失败 `created=0` |
| `reader_revision_get(store, id, &wire, &bytes, ...)` | 借用 ID | 输出由 `reader_revision_bytes_free` 释放 | 失败 `wire=NULL, bytes=0` |
| `reader_rs_decode(store, wire, bytes, record, error)` | 借用 wire 字节 | `record` 的字符串由 `reader_rs_record_free` 释放 | 失败后记录被清零并已释放 |
| `reader_rs_encode[_v2]` | 借用 envelope/capture | 输出由 `reader_rs_free` 释放 | 不可无损表示时 `wire=NULL, bytes=0`，并给出 gap |

线程/重入：`reader_revisions` 只允许创建它的 worker 串行调用（`READER_REV_OWNER`）；
本包不跨线程调用，也不在回调中重入。取消只覆盖 preferences 的控制回调；
revisions/reading-state 没有取消入口，测试不假装有。提交边界分别是：preferences 的
原子 rename、revision 的单个 SQLite 事务、reading-state 的纯内存编解码。

硬上限（既有预算，不放宽）：

- 设置文件 65536 字节（`max_file_bytes` 只能下调）。
- 一份修订原件 1 MiB、20000 个 JSON 值、32 层、32 个父 ID、每实体 4096 份历史。
- 选择器：exact 65536 字节、prefix/suffix v1 4096 字节、v2 128 字节/32 scalar；
  part_path/page_id/parser_version 各自限额；NUL 与非法 UTF-8 一律拒绝。
- 本包自己的边界：单目标 2500 次迭代或 90 秒（先到者），输入上限 70 KiB（设置）/
  300 KiB（wire），变异种子固定 `0x6A32332D66757A7A`。

## 组件

`tests/reader_app_boundary_fuzz/consumer/` 从**安装前缀**编译两个消费者：

- `boundary-c-consumer`（纯 C）：`defaults` / `status-name` / `load` / `validate-wire`，
  证明 C ABI 在无 C++ 运行时、无 try/catch 的翻译单元里可用。
- `boundary-cpp-consumer`（C++17）：全部具名命令、变异循环与单例回放。
  每个公开调用都被包在 `abi<>` 里：若 C++ 异常穿过 C ABI，进程以
  `{"violation":"C++ exception escaped ..."}` 退出 4，绝不转成业务状态。

变异引擎是 splitmix64 的固定实现，操作包括位翻转、字节覆盖、插入/删除/重复片段、
字典拼接、截断与截断到 1..32 字节填充；设置与 wire 各有一份字典。每次迭代先把
输入写到 `current.bin`，再在 `journal.log` 追加
`iter=<n> seed=<hex> base=<file> bytes=<n>` 并 flush，然后才执行被测调用——
这就是崩溃后的确定性重放入口。

## 具名检查（48 项，顺序与身份固定）

设置文件：`preferences.seed_manifest`（13 个夹具的期望状态在消费者读之前固定）、
`defaults`、`roundtrip`（保存字节与 canonical 逐字相同）、
`unknown_version_keeps_file`、`limit_ceiling`、`lower_limit`、
`nan_range`、`truncated_format`、`duplicate_key_format`、
`nul_string_format`、`unknown_enum_format`、`import_legacy_partial`、
`import_legacy_unknown_bits`、`import_legacy_invalid_merge`、
`status_names`（含 effective theme 与未知状态名）、`unicode_path`、
`empty_path`、`cross_process_reopen`。

wire：`wire.seed_manifest`（12 个夹具，含期望 SHA 与解码字段）、
`seed_v1_progress_valid`、`seed_v2_epub_annotation_valid`、
`unknown_field_format`、`duplicate_key_format`、`invalid_utf8_format`、
`byte_limit`、`hash_mismatch`、`pending_intent_local_then_ack`
（local 入队 → retry 固定 token → 错 SHA 拒 ack → 正确 ack 仅删队列 → 保留历史 →
重复 local 幂等且不重新入队）、`receive_idempotent_without_queue`
（远端 receive 只保留历史、**不产生本机 outbox**，重复接收幂等）、
`decode_v1_matches_seed`、`decode_not_reading_refused`、
`validation_does_not_write`（库文件 SHA 不变、历史 0、outbox 0）。

reading-state：`encode.v1_annotation_valid`、`encode.v2_point_valid`
（编码结果再交给 `reader_revision_validate`）、`encode.v1_chapter_scope_refused`、
`encode.v2_nul_refused`、`encode.argument_refused`。

跨进程与 C ABI：`cross_process.revisions_reopen`（多个独立进程读写同一产品库）、
`c_abi.parity`（C 与 C++ 消费者的默认值、状态名、加载/拒绝与 wire SHA 一致）。

模糊与确定性：`fuzz.{preferences,wire-validate,wire-decode,wire-receive,wire-local}.invariants`
与 `determinism.<target>`。每个目标的不变式：

- 状态落在文档集合内；错误消息在固定缓冲区内有 NUL 终止。
- 失败时不修改调用者记录（preferences），不发布陈旧 `info`（revisions），
  不留下半填 `record`（reading-state）。
- `receive`：`created` 为 0/1；成功或幂等时 outbox 行数都不变（远端到达不产生本机
  pending），成功时能用返回值立即读回逐字节相同的原件。
- `local`：`created` 为 0/1；成功时 outbox 恰好多一行，读回字节相同，且该行能被返回值中
  的 SHA 立即 ack 掉（历史保留）；失败或幂等时 outbox 行数不变。
- 每个真实崩溃/断言失败都从 journal 末行取回 `current.bin`，在两个全新进程中各重放一次，
  输出必须逐字相同，并作为 `replay.<target>` 具名结果记录。

## Actions 出口

单个 Linux 作业（`ubuntu-22.04`）：

1. 守卫：`HEAD == GITHUB_SHA`；固定起点为祖先；冻结 SDK 保护树、产品
   `001_catalog.sql` 与起点逐字相等；`git diff --name-only <start> HEAD`
   全在白名单（本文件、本包源码、本工作流、证据 JSON）。
2. 安装：产品目录（SQLite 3.54.0）→ revisions → preferences → 未改动的 reading SDK
   （`reading-library` preset）→ reading-state。其中 preferences/revisions/reading-state
   与消费者全部以 `-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g -O1`
   构建；ASan 自带 LeakSanitizer（`detect_leaks=1`），UBSan `halt_on_error=1`。
3. 安装头与源码逐字比对（三个应用头 + `exr/document.h`、`layout.h`、`library.h`）。
4. 从安装前缀编译 C 与 C++ 消费者（`-Wall -Wextra -Werror`），生成固定种子，
   跑具名检查、四个有界循环与全部回放。
5. 工件：日志、种子清单、驱动输出（含 `evidence/result.json` 与每个 case 的观察）、
   两个消费者二进制、安装头与静态库。严格作业重新下载同一 ZIP，重算字节数与
   sha256，逐项核对 48 个具名结果、五个 journal 摘要、消费者二进制摘要、安装头摘要、
   种子清单身份与 run/attempt/job 归属；任一缺项或跨源码即拒绝。

## 复现

```
cmake -S apps/reader/store/native -B build/fuzz-product -G Ninja -DCMAKE_BUILD_TYPE=Release   -DCMAKE_INSTALL_PREFIX=build/fuzz-stage
cmake --build build/fuzz-product --parallel 4 && cmake --install build/fuzz-product
SAN='-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -g -O1'
cmake -S apps/reader/revisions -B build/fuzz-revisions -G Ninja -DCMAKE_BUILD_TYPE=Release   -DREADER_PRODUCT_PREFIX=build/fuzz-stage -DCMAKE_INSTALL_PREFIX=build/fuzz-stage   -DCMAKE_C_FLAGS="$SAN" -DCMAKE_CXX_FLAGS="$SAN"
cmake --build build/fuzz-revisions --parallel 4 && cmake --install build/fuzz-revisions
cmake -S apps/reader/preferences -B build/fuzz-preferences -G Ninja -DCMAKE_BUILD_TYPE=Release   -DCMAKE_INSTALL_PREFIX=build/fuzz-stage -DCMAKE_C_FLAGS="$SAN"
cmake --build build/fuzz-preferences --parallel 4 && cmake --install build/fuzz-preferences
cmake --preset reading-library && cmake --build --preset reading-library
cmake --install build/reading-library
cmake -S apps/reader/reading-state -B build/fuzz-reading-state -G Ninja -DCMAKE_BUILD_TYPE=Release   -DEXR_SDK=build/reading-library/stage -DCMAKE_PREFIX_PATH=build/fuzz-stage   -DCMAKE_INSTALL_PREFIX=build/fuzz-stage -DCMAKE_CXX_FLAGS="$SAN"
cmake --build build/fuzz-reading-state --parallel 4 && cmake --install build/fuzz-reading-state
cmake -S tests/reader_app_boundary_fuzz/consumer -B build/fuzz-consumer -G Ninja   -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="build/fuzz-stage;build/reading-library/stage"   -DCMAKE_C_FLAGS="$SAN" -DCMAKE_CXX_FLAGS="$SAN"   -DCMAKE_EXE_LINKER_FLAGS="-fsanitize=address,undefined"
cmake --build build/fuzz-consumer --parallel 4
python3 tests/reader_app_boundary_fuzz/make_boundary_seeds.py build/fuzz-seeds
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=print_stacktrace=1:halt_on_error=1   python3 tests/reader_app_boundary_fuzz/run_boundary_fuzz.py   --consumer build/fuzz-consumer/boundary-cpp-consumer   --c-consumer build/fuzz-consumer/boundary-c-consumer   --fixtures build/fuzz-seeds --installed-prefix build/fuzz-stage   --sdk-prefix build/reading-library/stage --output build/app-boundary-fuzz
```

驱动只接受 `GITHUB_ACTIONS=true` 且断言 LeakSanitizer 与 UBSan halt 已启用；
本地不构建、不跑夹具、不解析工件。

## 发现缺陷时的归属

本包只报告，不修共享实现：保留最小输入（`work/fuzz/<target>/current.bin` 与对应
journal 行）、完整 sanitizer 栈与观察 JSON，并指明原模块 owner（preferences / revisions /
reading-state）与建议补丁方向。已经发现并保留的失败不会删除、不会改断言、不会换语料。

## 未覆盖范围

- 只授予 Linux Clang ASan/UBSan/LeakSanitizer × 一个作业；Windows、macOS、iOS、
  Android、GTK 宿主未构建、未运行。
- 不覆盖宿主 UI、主题观察者、产品接线、同步客户端、WebDAV 传输、两设备发现或冲突交互。
- encode 用例直接构造公开 selector 值，未加载真实文档；不声称 selector 已被 SDK 解析。
- 不修改冻结 SDK、产品 schema1、wire v1、anchor v1/v2，也不新增同步实体。

## 已保留的红轮（未删除）

- run `40126457981`（source `229c13ea`）：消费者以工作目录为 cwd 运行，而驱动把相对夹具路径
  原样传入，导致所有文件类检查立即失败（`preferences.defaults` 等无文件检查仍绿）。修复为
  解析绝对路径；原运行与工件保留。
- run `40127234053`（source `39f644a5`）：41/45 绿。`wire.receive_pending_then_ack` 与
  `cross_process.revisions_reopen` 暴露**本包自己的错误预期**：产品契约明确 `receive` 不产生
  outbox（只有 `local` 入队），而测试却要求 receive 入队。已按契约拆成
  `pending_intent_local_then_ack` 与 `receive_idempotent_without_queue`，并新增 `wire-local`
  模糊与确定性目标；不是把失败改成“预期拒绝”。
- run `40127808793`（source `b66f5f9c`）：52/53 绿，仅 `wire.receive_idempotent_without_queue`
  拒绝——所有 wire 种子共用同一个 revision id，接收第二个实体时命中同 ID 异字节的 COLLISION。
  这是夹具缺陷，不是产品缺陷：每个种子改为由 `sha256(entity_kind/entity_key/location_kind)`
  派生的独立 32 位十六进制 id，并保留该红轮与原始工件。
- run `40128307559`（source `bade50ae`）：53 个具名结果全绿，但验收仍为 `false`——驱动按
  `wire-validate` 这类带连字符的目标名登记 `fuzz.*`/`determinism.*`，而固定清单写成下划线，
  于是 8 项“缺失 + 多余”同时成立。严格作业正确拒绝；清单与目标名统一为连字符后重跑。

## 验收状态

**pending**：`accepted=false`。仅当同一 source/run/attempt 的 Linux 作业 48 项具名检查
（含四个模糊目标与四个确定性回放）全部成功、严格作业重算 ZIP 与内容摘要一致后才更新
`docs/validation/reader-app-boundary-fuzz.json`；本次记录之前任何生成物都不构成验收。
