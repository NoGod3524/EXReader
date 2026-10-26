# S20 六目标原生交付与启动检查

本包只做三件事，并把它们钉在同一次云端执行上：

1. **组装**：把各平台既有构建脚本的真实产出目录，包成用户能解压/安装的原生交付包
   （含 payload、`SHA256SUMS`、`manifest.json` 与中文短操作说明）。
2. **解包校验**：在全新临时目录解包，逐文件比对字节数与 SHA-256，重建可执行位，
   并复核包内 `SHA256SUMS` 与 manifest 自洽。
3. **启动与业务操作**：从解包后的真实程序出发，调用该平台既有的真实 UI 驱动，
   记录「本地导入 → 开书 → 翻页 → 设置 → 搜索/目录」里**实际观测到**的项。

构建、打包、UI 驱动、判据都属于原平台 owner。本包不重写它们，也不改 SDK、平台源码、
schema、根 CMake 或既有门禁。

## 1. 六个目标与复用入口

| 目标 | 原生建构（复用） | 交付形态 | 既有真实 UI 驱动（复用） |
| --- | --- | --- | --- |
| Windows | `cmake --preset reading-library` + `apps/reader/windows-account` | `EXReader-windows-<sha12>.zip` | `tools/check_windows_host.py`（158 动作）、`tests/reader_windows_search/check_ui.py`、`tests/reader_windows_navigation/check_ui.py` |
| Linux | `cmake --preset reading-library` + `apps/reader/desktop` | `EXReader-linux-<sha12>.zip` | `tools/check_linux_host.py`（20 项 X11）、`tests/reader_gtk_search/check_ui.py` |
| macOS | `tools/build_apple_host.py --platform macos` | `EXReader-macos-<sha12>.zip` | `tools/check_apple_host.py`（包体自检）、`tests/apple_host/EXReaderHostUITests.swift`（导入/翻页/排版）与 `tests/apple_host/search/ui` |
| iPhone | `tools/build_apple_host.py --platform simulator` | `EXReader-iphone-<sha12>.zip` | 同上（模拟器；`--device iphone`） |
| iPad | 同上 | `EXReader-ipad-<sha12>.zip` | 同上（`--device ipad`） |
| Android | `tools/build_android_host.py`（API34 x86_64） | `EXReader-android-<sha12>.zip`（含 APK 与夹具） | `tools/run_android_host_evidence.py`（45 例真实走查 + 两个原套件） |

打包脚本全部是原有的：`tools/build_windows_host.py`、`tools/build_linux_host.py`、
`tools/build_apple_host.py`、`tools/build_android_host.py`。

## 2. 交付包契约（`tools/reader_wave3_package/`）

- `assemble.py`：输入 `--payload <构建产出目录>`，输出
  `EXReader-<target>-<sha12>.zip`、`manifest.json`、`<zip>.sha256`、`安装说明-中文.md`。
  归档内固定含 `manifest.json`、`SHA256SUMS`、`安装说明-中文.md`，其它文件是 payload 原字节
  （仅 `--exclude` 显式声明的重复归档会被排除，并记录在 manifest）。
- `unpack.py`：`--into` 必须是**不存在**的目录；先核对外层 manifest 的归档字节数与 SHA-256，
  再解包、逐文件比对、重设可执行位、复核 `SHA256SUMS` 与包内 manifest 与外层一致。
- `delivery.py`：目标表、中文说明模板、清单元数据。
- 拒绝行为（自检覆盖）：短 SHA、重复输出、目标不符、归档被改一字节、解包目录已存在。

## 3. 执行入口

`.github/workflows/reader-wave3-s20.yml`：

- 触发：本包固定功能分支 push，或 `workflow_dispatch` 并给 `candidate_sha`（40 位十六进制）。
  `S20_CANDIDATE` 默认等于本次 run 的 `github.sha`。
- `guard`：`HEAD == candidate`、固定 seed `d263ce5228838ac90c0a0dc13a5193d4a7739681` 是祖先、
  `git diff --name-only seed HEAD` 全部落在本包白名单、SDK/平台/schema/根 CMake 逐字未改；
  随后 `py_compile` 全部本包脚本、`bash -n` 设备脚本，并跑离线归档契约自检。
- 六个生产者作业各自：守卫 → 构建 SDK 与产品前缀 → 用原打包脚本打包 → `assemble` →
  全新临时目录 `unpack` → 用解包后的程序跑原 UI 驱动 → `report.py` 出该目标矩阵 → 上传。
- `summary`：只下载本 run 本 attempt 的工件，调用 Actions API 核对名称/字节/摘要/有效期/
  `workflow_run.head_sha`，再从工件字节复算交付 ZIP 的 SHA-256，最后汇总六目标。

## 4. 目标报告（`s20-<target>/target.json`）

```
{
  "target": "...", "source_sha": "<candidate>", "sdk_version": "3.41.0",
  "entry": "<包内入口>", "entry_sha256": "...",
  "package": {"archive": {...sha256/bytes...}, "files": N, "checksums_checked": N},
  "drivers": [{"name","kind","report","sha256","checks","accepted","program_sha256"...}],
  "operations": {"import": [...], "open": [...], "page": [...], "settings": [...], "search"|"toc": [...]},
  "missing": ["..."], "problems": ["..."], "accepted": true|false
}
```

`accepted` 只在这四项（`import`/`open`/`page`/`settings`）与「`search` 或 `toc`」都拿到
**具名实测证据**、且驱动报告的 `source_sha` 与交付包内程序摘要都对得上时为 `true`。

## 5. 明确不做 / 不声称

- 不打 tag、不发 Release、不开 PR、不动默认分支；不做应用商店发布。
- 不给未签名 iOS 真机安装任何承诺：iPhone/iPad 只授予**模拟器**。
- Android 只授予 **API 34 x86_64 模拟器**，不授予真机。
- 不声称完整产品：`complete_product=false`；产品 schema 与冻结 SDK 未改。
- 不把缺证据的操作写成通过：缺项进 `missing`，目标即 `accepted=false`。

## 6. 复现

```bash
# 单目标（在对应 runner 上，由工作流调用）
python -m py_compile tools/reader_wave3_package/*.py tests/reader_wave3_s20/*.py
python tests/reader_wave3_s20/selftest.py
python tests/reader_wave3_s20/guard.py --output build/s20-guard/guard.json
python tools/reader_wave3_package/assemble.py --target linux --payload <构建产出> \
  --output build/s20-linux/delivery --source-sha <40hex> --sdk-version 3.41.0
python tools/reader_wave3_package/unpack.py --target linux \
  --archive build/s20-linux/delivery/EXReader-linux-<sha12>.zip \
  --manifest build/s20-linux/delivery/manifest.json \
  --into "$RUNNER_TEMP/s20-fresh-linux" --report build/s20-linux/unpack.json
python tests/reader_wave3_s20/report.py --target linux \
  --evidence build/s20-linux/evidence --unpack build/s20-linux/unpack.json \
  --output build/s20-linux/target.json
# 汇总（同一 run/attempt）
python tests/reader_wave3_s20/summary.py --targets build/s20-downloads \
  --source-sha <40hex> --output build/s20-summary/delivery.json
```

本仓库遵守「本地不构建/不测试/不处理工件」：以上全部在 Actions 里执行。

## 7. 本轮实测结果

受测源码 `63d0c8d2f032f5c78c77c9f407b17185412e991f`、run `40248648454` / attempt `1`：
Windows、Linux、macOS、iPhone **通过**；iPad（既有综合 UI 套件 12/13）与 Android（走查 3/45，
首个失败 `import_epub: import status missing`）**未通过**，整体 `accepted=false`。
逐目标身份、操作覆盖与失败原文见 `docs/reader-wave3-s20/validation.json` 与
`HANDOFF-RESULT-S20.md`。
