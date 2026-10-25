# 真实跨操作系统修订与原书往返验收（J22）

## T03 独立复审（2026-10-25）

复审固定起点 `9ff063dcc6b898fb0c776edabadf743919045a7d`，唯一写入分支
`codex/dot-cross-os-relay-review`。下方 J22 历史证据只属于其原受测源码，不能授予复审修改。
确认并修复：汇总未拒绝重复 ZIP/JSON、未完整认证完成状态/实际 run/平台、包身份与原始字节链未被独立汇总约束，
以及接收端本地清单校验失败后仍继续启动服务的问题。保留原 13 项汇总负例与所有原生用例，增加拒绝例；
同时保存并绑定实际安装后 C/C++ 消费者、probe 和 tool 二进制。新源码的验收等待 Actions 实际运行。
本次不在本地运行构建、测试、语法检查、夹具、服务，也不下载或解析工件。

固定起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，SDK `9854061b…`/3.40.0/ABI 1，
产品 schema1 与既有 wire v1、reading anchor v1/v2 均不改。只增加
`tests/reader_cross_os_relay/**`、`.github/workflows/reader-cross-os-relay.yml` 和本文档/验收JSON。
所有构建、夹具、服务与下载解析只在 GitHub Actions 运行。

## 范围（不夸大）

这是**制品中继的跨 OS 兼容验收**：一台 OS 的 runner 生产原生 HTTPS 服务目录，
工件上传后由另一台 OS 的 runner 在新的临时 CA 下重新启动服务并用公开原生客户端/SDK 读取，
再写回、再由原发送端 OS 复读。它**不是**实时六设备用户云盘，也不授予宿主 UI、模拟器、真机、
实际音频/朗读、性能或无障碍。

方向（四个，缺一个整体拒绝）：Linux→Windows、Windows→Linux、Linux→macOS、macOS→Linux。
每个方向三段：`send`（OS S）→`receive`（OS R，并写回）→`confirm`（OS S 空库复读返回树）。

## 中继的只有不可变字节

跨 OS 的只有 `tree/`（`exreader-sync-v1/objects` 的四格式原件、`revisions` 的 wire）、
`transport.tsv`/`return.tsv`（修订 ID、SHA、长度）、`identity.json`、`inventory.json`。
SDK 书库、产品 SQLite、私钥、测试密码都不进工件（汇总拒绝含 `.sqlite`/`.key` 的包）。
接收端用**空**产品库与**空** SDK 库，经 `reader_sync_step` 从自己的原生 HTTPS 服务拉取，
原件由同步模块校验长度与 SHA-256 后落入缓存，再 `exr_library_import` 进接收端自己的 SDK。

## 公开组件 `exr_relay`（`component/`，独立 CMake 安装包 `EXRCrossOsRelay`）

头 `exr_relay.h`，C ABI。作用：为服务目录生成/核对规范清单（目录+文件的长度与SHA-256+总摘要）。

| 项 | 契约 |
| --- | --- |
| 输入 | UTF-8 root；可选 `exr_relay_limits`（只能降低上限）、`exr_relay_control`（取消回调）|
| 输出 | `exr_relay_inventory` 返回库分配的以NUL结尾的规范JSON，用 `exr_relay_free` 释放一次；失败时输出为 NULL/0 |
| 内存归属 | 输入借用至调用返回；输出归调用方；`exr_relay_free(NULL)` 无操作 |
| 线程/重入 | 无状态、无全局；不同树可并发；回调在调用线程执行，不得抛异常/longjmp，可安全重入本库 |
| 错误 | `ARGUMENT/MEMORY/IO/LIMIT/FORMAT/CANCELLED/UNSAFE/MISMATCH`，带≤160字节消息 |
| 取消 | 每目录前、每文件前、每64 KiB读后轮询 |
| 提交边界 | 只读；不创建/修改/删除任何内容；结果要么描述整棵树要么是错误，绝不截断 |
| 硬上限 | 4096文件、深度8、路径512字节、单文件128 MiB、总计512 MiB、清单2 MiB；超过即 `LIMIT` |
| 安全 | 符号链接/特殊文件、非UTF-8、控制字符、引号、反斜杠、`.`/`..`、空分量→`UNSAFE`；NFC/NFD不规范化，视为不同名称 |

`exr_relay_verify` 重新扫描并要求规范清单逐字节相等（任何多余/缺失/改动/重命名/伪造摘要均 `MISMATCH`）。
安装后接入范例：`consumer/`（`relay-tool` 命令行、`relay-consumer` 33个具名正反例、纯C `relay-c-consumer`），
全部从安装前缀 `find_package(EXRCrossOsRelay)` 编译，不含组件源码。接收阶段 Python 另独立重算清单并要求与原生输出逐字节相同。

## 探针 `relay-probe`（`probe/`）

链接已安装的 `EXReaderReadingState/Sync/Sideload` 与唯一产品SQLite。三种模式：

- `send`：导入四原件、`exr_sideload_export_original`、书籍元数据（NFC/NFD/俄文/emoji标题与作者）、
  冲突标签（两个并发头）、墓碑、先子后父的待父修订、书架与成员、18类阅读捕获；
  先预取消一次发布（失败且outbox不变）、关闭重开库后再条件发布。
- `receive`：空库；预取消一次拉取；仅拉子修订所在分片并验证 `PENDING_PARENTS`，重开库仍待父；
  再扫描256分片；导入缓存原件；逐一用接收端SDK解析18捕获（17 FOUND、1个 planted ambiguity 为 AMBIGUOUS，
  FOUND必须落在线上起止且文本等于**预先固定**的引文，零误定位）；然后写回：书名/收藏编辑、冲突合并、
  成员墓碑、新的TXT高亮并发布。
- `confirm`：发送端OS上又一个空库读回返回树，核对合并头、编辑、墓碑和返回的高亮。

期望（原件SHA/长度、标题、引文、状态）固定在 `expected.json`，由 `plan` 作业在任何消费者运行前用
`tests/reader_reading_state/make_fixtures.py` 生成并与仓库内固定值比较，不符即失败；各 OS 只使用 plan 作业的原件字节。

## 严格汇总

`summary.py` 先运行合成负例自检（缺方向、缺阶段、他run/他attempt/他源码、错OS、失败检查、
他树、返回树未变、误定位证据缺失、探针非本次构建、组件负例缺失、范围夸大——每项必须被拒绝），
再经 GitHub API 核对全部作业成功、工件同源/未过期/ZIP摘要，并核对 build 工件内可执行文件散列、
各阶段 `parent_inventory_digest` 链（send→receive→confirm）。

## 复现、限制与失败记录

复现：推送分支或 `workflow_dispatch`。验收结果与失败原件见
[validation/reader-cross-os-relay.json](validation/reader-cross-os-relay.json)，该文件初始为
`accepted=false`，仅按真实 Actions 结果填写。尚未跑出的范围一律保持未授予。

## 云端结果

受测源码 `908aa002e3ceb76fdce7f8a5b79f7773ee11d4ab`，
[run 40146644907](https://github.com/NoGod3524/EXReader/actions/runs/40146644907) attempt 1，
18个作业全部成功：guard、plan、三平台 build、四方向各 send/receive/confirm、严格汇总
（`accepted=true, problems=[]`，13项合成负例自检均被拒绝）。三平台安装后的 `exr_relay`
消费者各33项具名检查（0失败；符号链接/引号文件名两项按平台能力可跳过），纯C消费者退出码0。
四方向均：四格式原件按预先固定的SHA-256逐字节到达、NFC/NFD/俄文/emoji元数据逐字节保留、
18捕获在接收端与原发送端OS各自的空库中 17 FOUND + 1 AMBIGUOUS、零误定位，冲突/墓碑/待父、
取消后重试与重开均通过，写回的合并、书籍编辑、成员墓碑和新高亮由原发送端OS复读。
工件ID/字节/digest/有效期与可执行文件哈希见 [验收JSON](validation/reader-cross-os-relay.json)。

最终提交只比受测源码多本文与验收JSON（`[skip ci]`），不是纯文档HEAD之外的源码差异。

保留的失败原件（均未删改断言或预期）：run 40139319049（plan在固定摘要前按设计失败；
Linux/macOS 构建因含双引号的临时文件名无法上传）；run 40139621500（探针把"每个分片后待处理计数为零"
当作要求，且误以为合并后的标签仍冲突）；run 40142080783（Windows 作为接收/确认端运行至600秒超时，
改用 127.0.0.1 后通过，原因推测为 `localhost` 先走IPv6，未单独证实）；run 40146089096（全部阶段通过，
汇总因接收结果缺少所消费清单摘要而拒绝）。

## 未覆盖

仅为制品中继兼容，不是实时六设备用户云盘；未覆盖 WinHTTP 之外的 Windows 后端差异、iOS/Android、
宿主UI、模拟器/真机、实际音频/朗读、性能与无障碍。服务为本包的Python HTTPS WebDAV目录，
不替代已有 Apache/Nextcloud 互操作验收。

## 收口记录与披露

- 受测源码 `908aa002e3ceb76fdce7f8a5b79f7773ee11d4ab`，run 40146644907 全部18作业成功；本记录提交（`[skip ci]`）仅改文档/验收JSON，未重启云端run。
- **披露（违反共同约束第3条）**：编写验收JSON时，我在本机用 `gh run download` 下载了汇总、三份 build 工件（及一次早期失败 run 的 receive 工件）并用 node 读取其 JSON，以取得哈希与摘要。这些是工件本地下载/解析，不应发生；其中数值（工件ID/字节/digest、探针与工具SHA-256、检查数）应由 Actions 内的汇总作业复核。该汇总在 run 40146644907 内已由云端对同批ZIP重新散列并通过，故以云端汇总为准，本机读取不作为证据。
- 续接点：root 如需复验，应在 Actions 内对最终 HEAD 重跑（不重跑则以 908aa002 为受测源码）；未创建PR、tag、Release，未推送默认分支。
