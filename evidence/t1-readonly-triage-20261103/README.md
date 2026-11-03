# T1 只读归因与 T4 前置方案 · 2026-11-03

T1 保持停手。本次只读已有 Git 对象、Actions 作业及日志，追加 evidence；零新 run、零 rerun。T4 只出方案，不修改版本号、SDK、workflow、登记或冻结锚点。本文结论仅用三态：**已证实 / 已否定 / 未证实**。

## 1. 四个失败作业的首错

对象：Required native reading SDK，run `41691589828`，attempt 1，分支 `preview/merge-audit-20261103`，源码 `769e509566204f53c0020ddbdb94d568bb571efe`。父提交依次为 `95100501eeef9c6325be8b3882aa400c99cf000f` 和 framework `8ca964fc4adc572cf2da303f5d88100a5e844ccb`。

逐项原文、时间戳、job ID 与失败 step 另存 [observations.json](observations.json)。以下每项仅摘首条错误（一行），不把 runner 的最终 exit-code 提示当首错。

### performance / reading-performance — job 126111282946

失败 step：`Measure fresh processes, selected reference pixels and evidence refusals`。

```text
{"accepted": false, "measurement_valid": false, "source_sha": "769e509566204f53c0020ddbdb94d568bb571efe", "run_id": "41691589828", "run_attempt": "1", "problems": ["SDK protected tree changed"], "results": null}
```

分类：**身份断言（protected tree）**。固定源码的 `tools/measure_reading_real.py:20` 钉 `SDK=9854061be331fe603a1822d9b2b36ee357154927`；`:544–545` 按 `PROTECTED` 顺序比较 Git 对象。第一项 `src` 已不同，所以在采样前拒绝；不是实测性能退化。

来源侧：合并的 `src` 对象 `e6bb1079cd50675a21ffe19cd99a6c08590eb3cf` 与 95100501 相同；性能固定对象为 `adc09002584fc20a99fd170e8148dbd870a27f52`，framework 也保持该对象。八项中 `src/include/cmake/CMakeLists.txt` 四项不匹配，另外四项匹配。完整比较见 [source-objects.json](source-objects.json)。这是 95100501 产品树与旧性能身份的冲突，不能归到本次语料冲突修复。

### native / apple-mobile — job 126111283266

失败 step：`Build and run the iPhone and iPad reference host`。

```text
build_apple_host.py: error: Installed SDK version differs from the explicitly selected version
```

分类：**身份断言（version）**。`tools/build_apple_host.py:60–61` 比较安装头文件的 EXR_VERSION 与 `args.sdk_version`。安装 SDK 为 `3.41.0`；脚本 `:36` 默认 `3.40.0`；native.yml 未传 `--sdk-version`，也未设置对应环境变量。此步在调用 Swift 编译前退出。

### native / desktop (macos-15) — job 126111283534

失败 step：`Build and run Swift host against installed SDK`。

```text
build_apple_host.py: error: Installed SDK version differs from the explicitly selected version
```

分类：**身份断言（version）**，与 apple-mobile 为同一断言和同一版本来源。此 step 中先前 Swift smoke 可成功；首错来自随后执行的 Apple host builder。

两条 Apple 臂的来源侧均为 95100501：`CMakeLists.txt`、`include/exr/base.h`、`tools/build_apple_host.py` 与 `native.yml` 在 95100501、合并树及合并前 ledger 后继 `a212dd59` 上分别为相同 Git 对象。framework 是 3.40.0，且其旧 Apple builder 尚无此显式版本断言，不能用其绿灯证明 3.41 调用契约已满足。

### native / desktop (windows-latest) — job 126111283484

失败 step：`Package and check the Windows reference reader`。

```text
FileNotFoundError: [Errno 2] No such file or directory: 'D:\\a\\EXReader\\EXReader\\build\\sdk-example\\Release\\exreader-reader-example.exe'
```

直接断点为 `tools/build_windows_host.py:63` 的 `shutil.copyfile(binary, payload/'EXReader.exe')`：native.yml 指定的打包输入不存在。此前 configure/build steps 成功，日志列出多个示例 exe，却没有该 reader exe。

分类：**三类中的编译/链接或环境根因均未证实**；已证实的是构建产物与打包输入契约不符。日志没有给出编译器/链接器错误，也没有下载、证书或超时首错；不能把 FileNotFoundError 改写成版本断言。产生该 exe 的更深原因保持未证实。

来源侧：此失败在合并前 `a212dd59` 的同名 job `126093483196` 已出现；`a212dd59` 相对 95100501 只有九个治理与 custody 新文件，未改 native.yml、示例 CMake 或 Windows builder。其打包输入契约来自 95100501 侧，不是本次 merge 新添的调用。

## 2. 不重跑的历史对照

| 来源 | 固定源码 / run | apple-mobile | desktop (macos-15) | desktop (windows-latest) |
| --- | --- | --- | --- | --- |
| 95100501 精确提交 | 95100501 / native.yml API head_sha 查询 | 无 run | 无 run | 无 run |
| 95100501 最新已运行祖先 | d66ffa4a7e1e53e56eef6609082c0296d0b13b99 / 40081814926 | success | success | success |
| 95100501 后继线、合并前且相关输入相同 | a212dd59975d5aa4256af7cc37d1bddd6b242dd1 / 41686485577 | failure：版本断言 | failure：版本断言 | failure：reader exe 缺失 |
| codex/framework 最近 native.yml | 8ca964fc4adc572cf2da303f5d88100a5e844ccb / 41178177640 | success | success | success |
| T1 合并树 native.yml 调用 | 769e509566204f53c0020ddbdb94d568bb571efe / 41691589828 | failure：版本断言 | failure：版本断言 | failure：reader exe 缺失 |

历史 job ID 与结论见 [observations.json](observations.json)。查询 native.yml 最近 100 条，按 Git 祖先关系筛出最近的 95100501 祖先执行；另对 95100501 完整 SHA 查询返回 `total_count=0`。祖先 d66ffa4a 的绿灯只覆盖自身。合并前后相关文件的完整 Git 对象对照见 [source-objects.json](source-objects.json)。

“两侧绿 + 合并红”的必要前提在当前版本不成立：framework 绿，而 95100501 没有精确提交 native run，相关输入相同的后继线已红。因而不能据此宣布 merge 引入这三项故障。

## 3. T4：从“稍后”改为 T1 前置（仅方案）

两条 Apple 平台臂确实命中版本身份断言，因此 **T4 版本身份单一真源列为 T1 前置**。下列位置均以受测合并源码 769e5095 为准，不套用 F03 3.42 分支的位置。

| 当前版本位置 | 准确行 | 当前值 / 消费者 |
| --- | --- | --- |
| `CMakeLists.txt` | 2 | `project(EXReader VERSION 3.41.0 LANGUAGES C)`；生成安装包版本 |
| `include/exr/base.h` | 17 | `#define EXR_VERSION "3.41.0"`；安装头文件及运行时版本 |
| `examples/CMakeLists.txt` | 9 | `find_package(EXReader 3.41.0 EXACT CONFIG REQUIRED ...)`；安装示例要求 |
| `tools/build_apple_host.py` | 35–36 | choices 3.40/3.41；默认 `EXR_APPLE_SDK_VERSION` 或 `3.40.0`；`:59–61` 读取头文件并比较 |

单一真源方案：新增 SDK 根 `VERSION` 为唯一可编辑产品版本；CMake 在 project 前读取它，生成公开头文件版本字段、安装包 EXReaderConfigVersion 与安装示例的期望版本文件。Apple builder 默认从同一来源读取期望值；独立安装包消费时读取随包携带的期望元数据，仍须与已安装头文件、包配置及二进制实际版本相等。显式 `--sdk-version`/环境输入只作为需核对的调用方声明，不得覆盖或绕过不匹配。组件各自版本、ABI 与性能固定 commit 不与产品版本混为一谈。

CI 负例设计（未实施、未运行）：在隔离工作副本保留 VERSION=3.41.0，仅人为把生成头文件 EXR_VERSION 改成 3.40.0；在同一次候选 CI 的版本一致性检查中要求非零退出，记录 `VERSION_IDENTITY_MISMATCH: VERSION=3.41.0, include/exr/base.h=3.40.0`。人为错误候选的版本门禁 job 必须以 failed 结束、整体 CI 变红；不使用 continue-on-error，也不把这次拒绝转成候选通过。正常构建不自动覆盖这处人为改动后再检查，否则负例失效。

先完成未来获批的 T4 一致性检查，再形成新的 refreeze 候选；性能 protected-tree 登记、Windows 缺失产物和独立验收仍分别处理。把 Apple 默认值硬改成 3.41.0、取消版本检查或更换分支都不能替代这些前置。

## 4. 三态结论

- **已证实**：T1 performance 是 protected-tree 拒绝；两条 Apple 臂是 3.41 安装 SDK 对 3.40 默认期望的拒绝；Windows 是 reader 打包输入缺失。相关冲突或契约均来自 95100501 侧并保留进合并树；T4 是 T1 前置，T1 继续停手。
- **已否定**：这四个首错证明了性能退化；Windows 首错也是 Installed SDK version differs；目前满足“两侧当前输入各自绿、仅合并后红”的归因条件。
- **未证实**：95100501 精确源码的 native 三臂绿灯、Windows exe 未生成的更深原因、T4 方案实施后的结果、新候选 refreeze 与 T1 验收结果。
