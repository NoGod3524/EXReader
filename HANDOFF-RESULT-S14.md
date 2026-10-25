# HANDOFF-RESULT-S14 — 既有字体库接入批准 SDK3.41

接收方：root。分支 `codex/reader-next-s14`，独立 worktree。交付状态：**accepted=false（未通过）**，
三轮完整 CI 已用完，全部失败与未验证项如实保留，见第 6、7 节。

## 1. 固定身份

| 项 | 值 |
| --- | --- |
| 固定起点 | `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8` |
| 复用的既有字体库 | `1563f4abb85ccd28c3a0aae3e9913f4330536215`（`apps/reader/font-library`） |
| 批准 SDK3.41 候选 | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（未接纳候选，接纳与同源终验归 root） |
| 冻结 SDK3.40 | `9854061be331fe603a1822d9b2b36ee357154927` |
| **被 CI 验证的源码** | `a27ab09dbabdac3371158f23ff827b06330d978b` |
| 本交接文件提交 | 见分支末提交（仅追加本文件，提交信息带 `[skip ci]`，不触发新 CI） |

模块源码树（`git rev-parse a27ab09d:apps/reader/font-library`）= `c25e82160e0a4e9fd3a531451d58a5a504a34bd5`。

## 2. 复用了什么，改了什么

复用的既有实现原样带入，**没有**第二套字体解析器、第二套存储、新产品 schema、raw API 或动态插件框架：

| 文件 | 与 `1563f4ab` 的关系 | git 对象 |
| --- | --- | --- |
| `include/reader_font_library.h` | 逐字节相同 | `e826dda45f600e9beeaa58fdb646ccedc46c252b` |
| `src/library.cpp` | 逐字节相同 | `01caf2af4ea8b6bfcba121e2348beb8282aaaa4d` |
| `src/sha256.hpp` | 逐字节相同 | `f55b62f6ec26dd4748ac12cbe9929c81a21ea760` |
| `CMakeLists.txt` | 仅加 `EXR_SDK` 前缀提示与 `EXR_SDK_VERSION`（默认 3.40.0，显式 3.41.0，其余值 `FATAL_ERROR`） | — |
| `EXReaderFontLibraryConfig.cmake.in` | 安装依赖改为 `find_dependency(EXReader @EXR_SDK_VERSION@ EXACT ...)` | — |

C ABI、`RFL1` manifest、字节语义、容量（16 MiB 字体 / 64 项 / 128 MiB 目录，硬上限 64/256/512 MiB，
32 个租约 / 128 MiB 编码字节）、取消阶段、路径与私有目录规则、导入失败不破坏既有字体、字体对象
owner/寿命规则全部未改。guard 与 harness 在 Actions 里重新计算上述三个文件的对象哈希，不等即拒绝出报告
（case `s14-reuses-pinned-module-bytes`）。

## 3. 旧 3.40 与当前 3.41 的安装差异（结论：无真实不兼容，只有构建描述不兼容）

- 字体公开面在两个 pin 之间**逐字节相同**：`include/exr/text.h`、`include/exr/font.h`、
  `include/exr/core.h` 及全部 `src/font*.c`/`src/fonts.c`/`src/pdf_font.c`
  （`git diff --exit-code 9854061b edddc463 -- <font surfaces>` 为空，Actions 内每轮复查，
  报告字段 `font_surface_unchanged` 必须为 true）。
- 两 pin 的全部差异 27 个文件：新增 `exr_render_page_background`（`render.h`/`raster.c`，纯追加，
  本包未用）、版本串 `EXR_VERSION 3.40.0→3.41.0`、`EXR_CORE_VERSION 3.39.0→3.40.0`、
  `project(EXReader VERSION 3.40.0→3.41.0)`，以及新测试与其 workflow。
- 唯一真实不兼容是 CMake 包版本：安装出的 `EXReaderConfigVersion.cmake` 是 `SameMajorVersion`，
  原模块写死 `find_package(EXReader 3.40.0 EXACT ...)` 并安装 `find_dependency(EXReader 3.40.0 EXACT ...)`，
  对 3.41.0 安装在两处都必然失败（`EXACT` 是字符串比较）。修法即本包的两处构建描述改动，
  与本树其它 reader 模块既有的 `EXR_SDK_VERSION` 约定一致。
- 详见 `docs/reader-next-s14/COMPATIBILITY.md`（含逐条命令与断言）；使用说明见
  `docs/reader-next-s14/README.md`。

## 4. Actions 证据（唯一证据来源）

- 工作流：`.github/workflows/reader-next-s14.yml`，仅 `push: branches: [codex/reader-next-s14]`。
- 第 3 轮（被验证源码）：run `40227758047` / attempt `1` / source `a27ab09dbabdac3371158f23ff827b06330d978b`。

| job | id | 结论 |
| --- | --- | --- |
| guard fixed source and replay verifier contracts | `121272683354` | success |
| font library (ubuntu-22.04, SDK341) | `121272683573` | success |
| font library (windows-2022, SDK341) | `121272683668` | success |
| font library (macos-15, SDK341) | `121272683512` | success |
| font library (ubuntu-22.04, SDK340) | `121272683535` | success |
| same-run S14 evidence and negative verifier cases | `121273397567` | **failure** |

原工件（同 run/attempt，证据 job 内下载 ZIP 后按 size/digest 复核；下方 digest 与 API 一致）：

| 工件 | id | bytes | SHA-256 | 到期 |
| --- | --- | --- | --- | --- |
| reader-s14-font-library-Linux-SDK341-40227758047-1 | 12611836423 | 10282223 | `be174b3becc6e42768e9155305170e431dccf4f0a5d99b9ec30196f04b256bc9` | 2027-01-23T19:48:17Z |
| reader-s14-font-library-Windows-SDK341-40227758047-1 | 12612191306 | 8783088 | `9f4ff959e8af62890346760afc1cef2cd686fede9fcddd0c8301ade1e322d2a0` | 2027-01-23T19:48:17Z |
| reader-s14-font-library-macOS-SDK341-40227758047-1 | 12611981106 | 9502521 | `96299bffd3b03241210b19fba15b6c02f8bc69d634f489b47aa2dbdf5d959ae9` | 2027-01-23T19:48:17Z |
| reader-s14-font-library-Linux-SDK340-40227758047-1 | 12612470782 | 10282533 | `4d16a320055a42f11105ad2262b2ae0c1d028680e6354c8b1cfe5013589ef34d` | 2027-01-23T19:48:17Z |
| reader-s14-font-verified-40227758047-1 | 12611504985 | 5567 | `1ecba105d7f7118afd9c1f850fb2669df0097b69a63b0b52ae40c358858b6f9d` | 2027-01-23T19:48:17Z |

程序与包身份（各作业原始二进制、静态模块、链接图，均由证据 job 重新哈希）：

| 平台/SDK | 静态模块 | font-probe | font-c | font-probe.map |
| --- | --- | --- | --- | --- |
| Linux/SDK341 | 150164 `4e54b843…f60d93` | 6809088 `ed9f5aec…6a82905` | 5488512 `bc44b6ca…102521d8` | 912731 `47b2c61f…0187778` |
| Windows/SDK341 | 1474668 `131c8903…c066c60c2c` | 4961280 `4ee7db18…bea7a2d9` | 3342336 `bcd8e13d…a69165edb2` | 3474565 `923c3607…24cdc18` |
| macOS/SDK341 | 95488 `f2b2b0b4…d5e7a99a3` | 5502904 `d4aea9a3…979b1867ff` | 4381192 `62859079…22e99aaa4` | 809480 `16bd330c…1c10bceb0` |
| Linux/SDK340 | 150164 `4e54b843…f60d93` | 6809088 `57555e7a…618ab937` | 5488512 `0e973d32…8a699afc` | 968678 `92bc7893…7a0d1f7e2` |

（完整 64 位哈希与全部身份项在每个平台工件的 `result.json` 的 `identities` 数组中，逐项 bytes/SHA-256 已被证据 job 复核。）

同源码绑定的其它身份：安装包配置 `de57ce33…315506`（Linux/macOS，1161 字节；Windows 因 CRLF 为 1459 字节，
哈希见其自身报告）、安装 SDK 头 `sdk-font-header.h` = `c6fb1add…be159cf`（17375 字节，等于所选 pin 的
`include/exr/text.h`）、安装 `EXReaderConfig.cmake` = `2110ca05…0f98025ad`。

## 5. 完整结果（第 3 轮被验证源码）

- 预检：guard（固定起点、受保护树与 3.41 候选树、冻结字体面、独占写入路径、workflow 触发分支、复用模块仅两文件差异）
  + 四个 harness 的 `py_compile` + 证据自检（合成数据集上 42 个负例全部被拒）→ success。
- 四个平台作业全部 success：安装所选 SDK（3.41.0 三平台；3.40.0 由 `git archive 9854061b` 隔离导出构建），
  默认 OFF 构型、可选静态包、安装后 C/C++ 消费者、原完整套 + 本包 S14 用例、真实进程终止、许可材料齐备。
- 每个平台的具名检查：Linux/macOS/Linux-SDK340 = 60，Windows = 61。
  原套 49 个 common 用例名与顺序语义未改，POSIX 2 个（`posix-source-and-directory-symlinks-rejected` 由 suite 打印、
  `posix-real-short-write-preserves-old` 由 harness 记录）或 Windows 3 个；本包新增
  `s14-unicode-path-duplicate-import`、`s14-invalid-font-preserves-selected-set`、
  `s14-reopen-unicode-directory-identity`（probe 的 s14 模式）与 6 个 harness 用例
  （`s14-installed-sdk-version-selected`、`s14-installed-package-binds-exact-sdk`、
  `s14-wrong-sdk-selection-rejected`、`s14-invalid-sdk-selection-rejected`、
  `s14-single-sdk-provider`、`s14-reuses-pinned-module-bytes`）。
- 真实失败与终止：Linux/macOS 各 27 条、Windows 32 条原生命令（含 3 条预期失败的 cmake 拒绝用例，Windows 另加
  被共享锁拒绝的 manifest 发布、junction 创建、以及一次 commit-uncertain 移除），4 个真实子进程在
  copy/validated/file-published/committed 处被杀，`returncode < 0`，
  重开后恢复集合与 readiness 文件一一对应。
- 证据 job：四个平台工件**全部通过** `validate()`（size/digest/秒级到期、ZIP 成员唯一、严格 JSON、
  用例集合精确、身份逐字节重算、命令角色与退出码、native 用例集合、终止记录、链接图、许可文本、单 SDK 绑定），
  随后在 42 个负例变异中的第 32 个 `forged-native-case` 失败 —— **验证器自身的缺陷**，见第 6 节第 4 条。

## 6. 保留的失败（不抹除、不放宽）

1. **run 40227167705 / attempt 1（source `f8cda2e6`）**：预检 job `121270877737` failure —
   证据自检合成数据把只有一行的命令日志写成 0 字节，`validate()` 报
   `ValueError: bound file changed: command-04.log`。
2. 同 run：证据 job `121271768371` failure — `ValueError: installed SDK config binding`。
   根因：Windows 安装出的 `EXReaderConfig.cmake` 是 CRLF（1459 字节），harness 用文本 round-trip 计算 SHA-256
   得到 LF 版本的哈希，与原始字节不符。已改为两侧都按原始字节哈希。
3. **run 40227593311 / attempt 1（source `ec6b3bb7`）**：预检 job `121272171212` failure —
   `SyntaxError: unterminated string literal (detected at line 385)`（编辑时把换行写进了字符串字面量）。
4. **run 40227758047 / attempt 1（source `a27ab09d`）**：证据 job `121273397567` failure —
   `AssertionError: verifier accepted forged-native-case`。负例变异用 `commands[1]` 定位 suite 日志，
   而本轮 harness 的命令顺序是 c-consumer → 3 条预期失败的 cmake 拒绝 → suite → s14，
   `commands[1]` 落在 `configure-invalid-sdk` 日志上，改动被同步更新身份后无人发现，于是负例被“接受”。

## 7. accepted=false 与未验证项

- **本包未被接纳**：证据 job 红，严格同源验收未跑完（`accepted=false`，summary 中 `failures=["AssertionError('verifier accepted forged-native-case')"]`）。
  四个平台工件本身已通过 `validate()`；失败点在验证器对自己的负例变异。
- 42 个负例中 31 个被正确拒绝，第 32 个漏过；**第 33~42 个在真实数据上未执行**（自检只在合成数据上跑过）。
- 已知修复（**未应用、未验证**，为保持“被验证源码”与证据一一对应，本次不改树）：
  1. `tests/reader_next_s14/verify.py` 的 `altered-native-log` / `forged-native-case` / `missing-native-command`
     改为按 `role='suite'` 取日志与命令，不用 `commands[1]`；
  2. `synthetic()` 的命令顺序改成与真实 harness 一致（suite/s14 在前、cmake 拒绝项在后），
     否则自检永远看不到这个错位。
- 交 root 的部分：字体选择器 UI 与设置接入（未做，不改共享 preferences/宿主/SDK）。
- SDK3.41 仍是**未接纳候选**：本包只安装、链接并记录其树哈希，最终接纳与同源终验由 root 执行。
- 未声明能力：断电/文件系统/控制器持久性、网络共享、TTC 全面枚举（只做显式 face 选择）、主机 UI 与移动端集成。

## 8. 边界声明

- 只写 `apps/reader/font-library/`、`tests/reader_next_s14/`、`.github/workflows/reader-next-s14.yml`、
  `docs/reader-next-s14/`、`HANDOFF-RESULT-S14.md`；未改冻结 SDK、受保护测试、其他 owner、宿主与旧裁判
  （guard 每轮在 Actions 复查）。
- 构建、语法、测试、夹具与工件下载/解包/解析全部只在 GitHub Actions；本地只用 git 读取源码与日志错误段。
  说明：写作阶段曾本地执行过一次 `py_compile` 用于自检，未作为任何验收证据；验收证据全部来自上表 run。
- 单 SDK/provider：每个作业只装一个 SDK，安装包配置里只有一个 `find_dependency(EXReader <version> EXACT ...)`，
  导出目标只引用 `EXReader::exr_core`；用另一版本配置会在 configure 阶段失败（3 条预期失败用例）。
- 测试资料仅 Adobe Source Serif 4.005R（`adobe-fonts/source-serif@2823e993c53fca27c5c8749f529b56a5a7c77b6b`），
  许可 **SIL Open Font License 1.1 (OFL-1.1)**，三个 Git blob 身份与字节数在 `run.py` 内固定并在 Actions 复核；
  TTC 由该 TTF 在 Actions 内用 `fonttools 4.58.0` 生成；无第三方字体进入产品。
- 未派子代理，未用 cpuse，未开 PR、未打 tag/Release，未推默认分支。
