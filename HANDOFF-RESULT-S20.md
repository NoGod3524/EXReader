# HANDOFF-RESULT-S20：六目标原生交付流水线与启动检查

**结论：四目标通过（Windows / Linux / macOS / iPhone），两目标未通过（iPad / Android），整体 `accepted=false`。**
六个原生交付包都在**同一次 run、同一个 attempt** 里由同一个不可变 candidate 组装、解包、启动并留下具名证据；
两处未通过是既有产品面/驱动面的真实失败，原样保留，没有改写成通过。

## 1. 身份

| 项 | 值 |
| --- | --- |
| 固定 seed | `d263ce5228838ac90c0a0dc13a5193d4a7739681` |
| 分支 | `codex/reader-wave3-s20`（仅功能分支；无 PR/tag/Release，默认分支未动） |
| workflow | `.github/workflows/reader-wave3-s20.yml`（本分支 push + `workflow_dispatch` 的 `candidate_sha` 输入） |
| **受测源码 SHA** | **`63d0c8d2f032f5c78c77c9f407b17185412e991f`** |
| run / attempt | **`40248648454` / `1`** |
| 作业 | guard `121335510732`；Windows `121335559152`；Linux `121335559151`；macOS `121335559172`；iOS `121335559096`；Android `121335559092`；summary `121350102491` |
| 阅读 SDK（未改） | 3.41.0 / ABI 1（安装后公共头、ConfigVersion 与探针一致） |
| 产品 schema | 未改 |

守卫在每个作业首步执行：`HEAD == candidate`、seed 是祖先、`git diff --name-only seed HEAD` 全部落在
`tools/reader_wave3_package/`、`tests/reader_wave3_s20/`、`.github/workflows/reader-wave3-s20.yml`、
`docs/reader-wave3-s20/`、`HANDOFF-RESULT-S20.md`；SDK/平台/schema/根 CMake/README 逐字未改
（守卫输出 `accepted=true, changed=11`）。

## 2. 交付内容（全部新增，未改任何平台或既有门禁）

- `tools/reader_wave3_package/`：`delivery.py`（目标表/中文说明模板/清单）、`assemble.py`（打包含
  `SHA256SUMS`、`manifest.json`、`安装说明-中文.md`）、`unpack.py`（全新目录解包并逐文件校验、
  重设可执行位、复核包内清单与 `SHA256SUMS`）。
- `tests/reader_wave3_s20/`：`guard.py`（seed/candidate/独占路径）、`selftest.py`（离线契约自检，
  含 5 类拒绝）、`report.py`（把既有驱动的具名检查映射成操作矩阵）、`xctest.py`（跑既有 Apple UI 套件并
  记录具名用例）、`summary.py`（同 run/attempt 工件认证与六目标汇总）、`android_device.sh`。
- `.github/workflows/reader-wave3-s20.yml`：guard + 五个生产者作业（Windows/Linux/macOS/iOS/Android）+ 严格汇总。
- `docs/reader-wave3-s20/README.md`、`docs/reader-wave3-s20/validation.json`。

**复用的既有脚本（未改一行）**：`tools/build_windows_host.py`、`tools/build_linux_host.py`、
`tools/build_apple_host.py`、`tools/build_android_host.py`、`tools/check_windows_host.py`、
`tools/check_linux_host.py`、`tools/check_apple_host.py`、`tools/run_android_host_evidence.py`、
`tests/reader_windows_search/check_ui.py`、`tests/reader_windows_navigation/check_ui.py`、
`tests/reader_gtk_search/check_ui.py`、`tests/apple_host/*`（含 13 例综合 UI 与 4 例搜索 UI）。

## 3. 六目标实测（同一 source / run / attempt）

| 目标 | 结论 | 包内入口 | 入口 SHA-256 | 交付包 | 字节 | 交付包 SHA-256 | 驱动 | 实际观测到的操作 |
| --- | --- | --- | --- | --- | ---: | --- | --- | --- |
| Windows | **通过** | `EXReader/EXReader.exe` | `dc30bdcd…27a672` | `EXReader-windows-63d0c8d2f032.zip` | 17,372,224 | `262092c6…b1d1c748` | 158 动作计划 + 搜索 13 项 + 目录 | import/open/page/settings/**search**/**toc** |
| Linux | **通过** | `EXReader-Linux/bin/exreader-linux` | `7e763ad5…b710d9` | `EXReader-linux-63d0c8d2f032.zip` | 18,264,801 | `fbe17e55…a96784e` | 20 项真实 X11 + 书内搜索 | import/open/page/settings/**search** |
| macOS | **通过** | `EXReader.app/Contents/MacOS/EXReader` | `22bfb154…54dd4e` | `EXReader-macos-63d0c8d2f032.zip` | 27,005,409 | `2a10ab14…4dd5e8` | 包体自检 + 综合 UI 13/13 + 搜索 UI 4/4 | import/open/page/settings/**search** |
| iPhone | **通过** | `EXReader.app/EXReader` | `96e0a01e…e5d5a` | `EXReader-iphone-63d0c8d2f032.zip` | 27,018,537 | `357762f4…b6ccdfe` | 模拟器安装自检 + 综合 13/13 + 搜索 4/4 | import/open/page/settings/**search** |
| iPad | **未通过** | `EXReader.app/EXReader` | `96e0a01e…e5d5a` | `EXReader-ipad-63d0c8d2f032.zip` | 27,018,532 | `0e201871…69ecd6d` | 模拟器安装自检 ✓、搜索 4/4 ✓、**综合 UI 12/13** | 五项操作均由通过的驱动观测到，但综合套件有 1 例失败 → 不授予 |
| Android | **未通过** | `artifacts/app-debug.apk` | `c0e7528e…ed4d6a` | `EXReader-android-63d0c8d2f032.zip` | 70,151,353 | `2ef256c5…92607f` | API34 x86_64 走查 **3/45** | 无（首个失败 `import_epub`：`import status missing`） |

- 每个包都先解包到**全新临时目录**，逐文件比对字节数与 SHA-256、重设可执行位、复核包内 `SHA256SUMS` 与外层 manifest。
- 驱动的 `source_sha` 与「实际程序摘要」都和交付包内入口摘要对上：Windows 三个驱动均回报同一
  `consumer_sha256`；Linux 搜索驱动回报 `program_sha256`；Apple 自检回报 Info.plist 的 `EXRSourceSHA`；
  Android 设备报告回报的 APK 摘要等于交付包内 `artifacts/app-debug.apk`。

## 4. 两处未通过的真实内容

**Android（既有宿主，C11 归属）**：三个 instrumentation 套件退出码都是 0，但 `device/validation.json`
记录 **45 例中仅 3 例通过**；首个失败是 `import_epub`（`AssertionError: import status missing`），
随后 `open_epub`（`book row not found: Sample.epub`）。夹具确实被推到 `/sdcard/Download`
（`device-downloads.txt` 列出 15 个文件、字节数正确），因此这不是「没推文件」，而是默认构建的 Android 宿主
在 API34 x86_64 上导入路径未产生状态。另：Android 交付包不含「书内搜索/目录」（默认构建
`BuildConfig.READER_SEARCH=false`），所以即使走查通过，`search_or_toc` 也只能记为缺口。

**iPad（既有 Apple UI 套件）**：本轮综合套件 13 例中 **12 通过 / 1 失败**（`exit=65`）；同一套件在前一轮
（`979a34b5`，run `40245971457`）在 iPad 上 **13/13** 通过，因此至少是**间歇性**失败。失败用例名未落进
作业日志尾部（尾部只有 `** TEST FAILED **` 与 `ipad.xcresult` 路径）；完整用例列表在工件内的
`ipad-xctest-broad/ipad.xcresult` 里。同一轮 iPad 搜索套件 4/4 通过、包体自检通过。
按「不把缺一项写成通过」的规则，iPad 不授予（`report.py` 仍把它实际观测到的五项操作原样记录）。

## 5. 四轮云端记录（原样保留）

| run | 受测源码 | 阶段 | 结果 |
| --- | --- | --- | --- |
| 40245766789 | `b4002e7c` | guard | 失败：离线归档自检发现包内/外层 manifest 不一致（归档清单里多了 `archive:null` 键） |
| 40245894358 | `d9d4b75a` | guard | 失败：离线自检用的合成 payload 没有声明入口；另发现汇总把 web 主机当 REST 基址（已改 `GITHUB_API_URL`） |
| 40245971457 | `979a34b5` | 生产者 | Linux ✓、macOS ✓、iPhone ✓；Windows 目录驱动缺 `uiautomation` 依赖；Android 构建被「3.41 SDK 树 ≠ 冻结 3.40 基线」拒绝；iPad 搜索 3/4（`testNoHitPreservesReader`） |
| **40248648454** | **`63d0c8d2`** | 生产者 + 汇总 | Windows ✓、Linux ✓、macOS ✓、iPhone ✓；iPad 综合 12/13；Android 走查 3/45；汇总 `accepted=false` |

前两轮是守卫阶段（没有生产者作业启动），后两轮才是完整轮。四次失败的原始日志与工件都没有被改写。

## 6. 工件身份（同 run `40248648454` / attempt `1`）

| 工件 | ID | 字节 | GitHub 摘要 | 过期时间 |
| --- | ---: | ---: | --- | --- |
| `reader-wave3-s20-windows-40248648454-1` | 12619553422 | 18,801,304 | `sha256:3b9f9a67…e821c8` | 2027-01-24T00:17:40Z |
| `reader-wave3-s20-linux-40248648454-1` | 12619273158 | 18,802,425 | `sha256:48534b45…f0dcc298` | 同上 |
| `reader-wave3-s20-macos-40248648454-1` | 12620028953 | 255,889,637 | `sha256:3d80a6d7…5fe5f7c` | 同上 |
| `reader-wave3-s20-iphone-40248648454-1` | 12620818585 | 36,932,446 | `sha256:b3251990…18c97d7` | 同上 |
| `reader-wave3-s20-ipad-40248648454-1` | 12620563919 | 171,909,007 | `sha256:2237f3d3…d3f4f8b9` | 同上 |
| `reader-wave3-s20-android-40248648454-1` | 12620640994 | 95,759,865 | `sha256:bee79488…86be15d4` | 同上 |
| `reader-wave3-s20-summary-40248648454-1` | 12621204821 | 2,281 | `sha256:e520a4c3…27ba199` | 同上 |

汇总作业用 Actions API 认证名称/字节/摘要/有效期/`workflow_run.head_sha`，再从**工件字节**
复算每个交付 ZIP 的 SHA-256，并要求目标报告与内层 manifest 的入口摘要一致；
`delivery.json` 的 `accepted=false`，`problems=["android: target report is not accepted","ipad: target report is not accepted"]`。

## 7. 未验证 / 不声称

- 未开 PR、未打 tag/Release、未动默认分支、未做商店发布；`complete_product=false`。
- iOS 只授予**模拟器**：未签名 `.app` 不能装真机，本包也没有真机证据。
- Android 只授予 **API34 x86_64 模拟器**；真机、arm64、其他 API 未验证。
- 无任何性能、无障碍读屏、签名/公证、安装器（deb/rpm/msi）结论。
- iPad 与 Android 的五项操作覆盖：iPad 五项都由通过的驱动观测到但综合套件 1 例失败；
  Android 走查本身失败，五项均未观测到。

## 8. 接入与复现

```bash
# 用最终产品 source 跑同一入口（candidate 必须是 40 位十六进制，且等于被 dispatch 的 ref 的 HEAD）
gh workflow run reader-wave3-s20.yml --ref <branch-or-sha-ref> -f candidate_sha=<40-hex>

# 本地契约自检（在 Actions 里由 guard 作业执行，等价命令）
python -m py_compile tools/reader_wave3_package/*.py tests/reader_wave3_s20/*.py
python tests/reader_wave3_s20/selftest.py
python tests/reader_wave3_s20/guard.py --output build/s20-guard/guard.json

# 单目标组装/解包/矩阵（平台 runner 上）
python tools/reader_wave3_package/assemble.py --target linux --payload <构建产出目录> \
  --output build/s20-linux/delivery --source-sha "$S20_CANDIDATE" --sdk-version 3.41.0
python tools/reader_wave3_package/unpack.py --target linux \
  --archive build/s20-linux/delivery/EXReader-linux-<sha12>.zip \
  --manifest build/s20-linux/delivery/manifest.json --into "$RUNNER_TEMP/s20-fresh-linux" \
  --report build/s20-linux/unpack.json
python tests/reader_wave3_s20/report.py --target linux \
  --evidence build/s20-linux/evidence --unpack build/s20-linux/unpack.json \
  --output build/s20-linux/target.json
```

**需 owner 处理（不由本包改）**：Android 宿主在 API34 x86_64 默认构建下的导入路径（`import status missing`）；
Android 宿主是否提供书内搜索/目录；iPad 综合 UI 套件的 1 例间歇失败（建议 owner 在 workflow 里把
`xcresult` 的具名用例列表落盘，本包只在失败时才打印日志尾部，抓不到该用例名）。

## 9. 说明

本文是 `[skip ci]` 的纯证据提交，不触发新的功能测试；受测源码仍是 `63d0c8d2f032f5c78c77c9f407b17185412e991f`。
