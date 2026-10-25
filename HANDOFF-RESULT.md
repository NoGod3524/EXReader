# S10 电脑传书入口与能力证据 — 交回状态

状态：**进行中**（workflow 已提交，等待实际 Actions 结果；本文件在得到真实 run 后更新为最终值）。

- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`
- 分支：`codex/reader-fw-s10`
- 独占路径：`tests/reader_final_s10/`、`.github/workflows/reader-final-s10.yml`、
  `docs/reader-final-s10/`、本文件
- 契约与用户步骤：`docs/reader-final-s10/CONTRACT.md`
- 验证汇总：`docs/reader-final-s10/validation.json`（未执行前 `accepted=false`）

## 已实现

1. `tests/reader_final_s10/check_guards.py`：所有权守卫。要求 `HEAD==GITHUB_SHA`、起点是祖先、相对起点的
   改动只落在本包四个路径、`apps examples src include cmake CMakeLists.txt bindings tests/fixtures extras
   tools docs/validation .github/workflows`（除本包 workflow）全部字节不变，并含接受/拒绝两类路径反例。
2. `tests/reader_final_s10/check_entries.py`：20 项真实声明检查（Android manifest/SAF owner、Apple
   Files 共享钥匙与安全作用域 owner、macOS/Windows/GTK 桌面入口、WebView/监听套接字禁令）+ 13 个具名
   变异反例；每个变异必须恰好让声明的检查失败（不多不少），否则本包失败。
3. `tests/reader_final_s10/make_fixtures.py`：只在 CI 生成 fixture（EPUB/TXT/PDF）并记录字节与 SHA-256。
4. `tests/reader_final_s10/android/`：真实 SAF `DocumentsProvider` + `ACTION_VIEW` 授权发送器，把模拟器上
   的真实文件交给既有导入 owner `extras/android-import-entry`（未改动）。
5. `tests/reader_final_s10/apple/main.swift`：iOS/iPadOS 模拟器驱动，仅调用既有 owner
   `HostReaderModel.importFile(url:)`（含 `startAccessingSecurityScopedResource`）。
6. `tests/reader_final_s10/desktop/`：消费 `extras/desktop-drop` + `extras/sideload` 的真实 `text/uri-list`
   入口，导入并 `exr_sideload_export_original` 导出原件。
7. `tests/reader_final_s10/authenticate_artifacts.py` + `summarize.py`：只读取本 attempt 已认证的工件 ZIP，
   拒绝混源、缺平台或未认证结果，产出 `validation.json`。

## 待真实 run 后填入

受测 SHA、docs-only 封存 SHA、run/attempt、各 job 与 artifact 的 ID/字节/SHA-256/有效期、实际检查项、
原失败与未验证项（真机与 USB/MTP、Files 传输、选择器 UI、Windows/macOS 可执行运行）。
