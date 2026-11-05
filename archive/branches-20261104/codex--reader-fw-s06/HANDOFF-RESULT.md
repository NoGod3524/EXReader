# S06 六目标导入入口真实回归矩阵 —— 交回

分支 `codex/reader-fw-s06`，实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。
本包只新增 `tests/reader_final_s06/`、`.github/workflows/reader-final-s06.yml`、
`docs/reader-final-s06/` 与本文件；宿主/SDK/原 tests/原 workflow/预算/保护树一行未改
（guard 作业对 `git diff --name-only <base> HEAD` 做了白名单校验）。

## 1. 身份

| 项 | 值 |
| --- | --- |
| 受测实现源码 | `e1580354d7c3e11dabe351eb63049a686b651821` |
| docs-only 封存 | 本文件与 `docs/reader-final-s06/` 所在提交（`e1580354` 之后的文档提交；其自身 SHA 见分支 tip，文件无法包含引入它的提交哈希） |
| 远端分支 | `origin/codex/reader-fw-s06` |
| workflow | `.github/workflows/reader-final-s06.yml`（只在本分支 `tests/reader_final_s06/**` 与自身路径变化时触发） |
| run / attempt | [40215584275](https://github.com/NoGod3524/EXReader/actions/runs/40215584275) attempt **1**，5/5 作业 success |

作业：guard `121235891876`；windows `121235946182`；linux `121235946186`；
macos `121235946248`；strict same-run matrix `121237344599`。

## 2. 结论

矩阵 **21 个单元 pass / 0 fail / 0 blocked / 21 pending**，编译器 `accepted=true`、`complete=false`。
实跑三个桌面目标各 **38 个具名 case 全过、`__summary failed=0`**；`android / iphone / ipad` 三目标逐单元
pending 并带具体原因。移动目标不授予任何东西，完整产品授予由 root 控制（`task_wide_accepted=false`）。

| 目标 | runner | 7 单元 |
| --- | --- | --- |
| windows | windows-2022 | 全 pass（38/38） |
| linux | ubuntu-22.04 + GTK3 + Xvfb | 全 pass（38/38） |
| macos | macos-15 | 全 pass（38/38） |
| android / iphone / ipad | — | 全 pending（原因见第 6 节） |

七单元：`local_file`、`system_open_share`、`cloud_download_to_sideload`、
`duplicate_same_original`、`bad_file`、`nine_formats_original_identity`、
`entry_cancel_and_reopen`。契约见 `docs/reader-final-s06/MATRIX.md`，
逐项结果见 `docs/reader-final-s06/validation.json`。

## 3. 实际做了什么（不是模块冒名 host）

探针 `s06-matrix-probe` 只链接**安装后的**冻结 SDK 3.40 书库、`extras/sideload` 与
`extras/desktop-drop`，不改它们一行：

- **系统打开/分享**：探针自己写真实操作系统交接载荷，再经安装的适配器读回，然后导入被交接的那条路径。
  Windows 是 CF_HDROP（回读得到 `D:\a\EXReader\...\handoff\pasted.epub`，kind 1 = FILE）；
  Linux 是 X11 `text/uri-list`；macOS 是 NSPasteboard file URL。目录记 kind 2 且不导入，
  不存在的路径记 kind 9，两条目时 `2 items / 1 files`。
- **云盘下载 → sideload**：Actions 内用 `curl` 从固定 commit 取 `sample.epub` 与
  `pdf-public.pdf`，下载字节与仓库 fixture `diff` 相同（探针再核 SHA-256），把**下载副本**
  送进 sideload：新的一本 `created=1`，而库里已有的同一原件 `created=0` 且 id 不变。
- **已有同一原件重复**：同路径与改名副本都 `created=0`、id 相同、书数不变；标题、进度（position 7、
  favorite）、标注都保留；重投时取消不伤旧书且旧原件逐字节仍可读。该单元刻意跑在 memory 路由的原件上，
  因为 bounded EPUB 模式本来就没有旧的全局进度/标注接口。
- **坏文件**：截断（1084→361 字节）、512 字节随机垃圾、0 字节、不存在四项分别 `EXR_FORMAT` /
  `EXR_FORMAT` / `EXR_FORMAT` / `EXR_IO` 显式拒绝，零新增行，旧原件仍逐字节可读。
- **九格式 + 原件身份**：TXT/HTML/FB2/EPUB/DOCX/RTF/MOBI/PDF/CBZ 各一次导入、原件逐字节回读、
  二次导入去重、私有原件导出（`exr_sideload_export_original`）逐字节相同，最后关库重开 9 本仍在。
- **取消前后零 / 已提交语义**：提交前取消 memory 与 stream 两条路由都零新增行；第二次导出不覆盖既有文件
  （SHA-256 前后一致）；关库重开 6 本、已提交原件仍逐字节相同。

原件 SHA-256（探针实测，三平台一致）：
`sample.txt fe0e65a9…`、`sample.html 84ebc6d4…`、`sample.fb2 f3e4be66…`、
`sample.epub 0f871f44…`、`sample.docx 1abfda17…`、`sample.rtf b562f2d1…`、
`sample.mobi 2a3d3b81…`、`pdf-public.pdf 4f6fdc7b…`、`comic.cbz 08df7ceb…`。
完整 64 位值见 `validation.json` 的 `original_sha256`。

## 4. 工件（同一 run/attempt，均已认证）

| 工件 | id | 字节 | SHA-256 | 有效期 |
| --- | --- | --- | --- | --- |
| guard | 12607790219 | 47834 | `2eb8cbcf62934219e0569e386f6ddd6942a338f114b7d287ff1bb2668bbc3c9a` | 2027-01-23T17:15:29Z |
| evidence-windows | 12607316814 | 3042428 | `81e325678bf26045691dc37cd3cd0ebda3ec1621ac17d76a5212460895ceeb9b` | 同上 |
| evidence-linux | 12607780698 | 4078229 | `2a4c0d2d62fe578d3de8eea68b13d87a97409081fa4bd0456d91f085963db13e` | 同上 |
| evidence-macos | 12607456931 | 3484464 | `a04dea76f7db27d4515f4524e6b48e1a429a98501f5c087b3eaffb8f981e191e` | 同上 |
| report | 12607262286 | 2425 | `b47985c53b22de0fbaeac92f287e2fb7341ad08557ef545a12d79da541224e10` | 同上 |

真实程序哈希（编译器从同一工件重新哈希）：

| 目标 | 探针二进制 | 探针 JSONL |
| --- | --- | --- |
| windows | `a68506b8f0b512badbbe1022efe59887a30b94c769197362510e9d059027a715`（6,063,616 B） | `e5a83b97…`（5,741 B） |
| linux | `b504bcb734833af8a225a440d512420f84035999aae60e5c10301a653fdee700`（8,509,608 B） | `13f75588…`（5,746 B） |
| macos | `ea4ecc31999668ed824cd8b601438aa90425876df59d54bd2b0e862b0bc16f80`（6,948,896 B） | `80c2f414…`（5,751 B） |

## 5. 保留的原失败（不并入通过）

| run | attempt | 作业 | 根因 | 处理 |
| --- | --- | --- | --- | --- |
| 40214566799 | 1 | guard 121232804941 | 编译器自检里 `refuses_failed_required_case` 要求一个编译器本就不产生的全局 problem（它记 failed cell）；12 例里 11 过 | 自检改为直接断言失败单元集合 |
| 40214791827 | 1 | windows 121233507310 | 探针分片缺 `<shlobj.h>`，MSVC 下 `DROPFILES` 未声明 | 补 include |
| 40214791827 | 1 | macos 121233507381 | 探针分片缺 `<exr_desktop_drop_apple.h>`，`exr_drop_apple_request_from_pasteboard` 未声明 | 补 include |
| 40214791827 | 1 | report 121234926268 | 正确拒绝：windows/macos 声明可测却无证据 | 无（这是期望行为） |

同 run 的 linux 作业在 40214791827 里已经 38/38 通过，**没有**把那一轮结果拼进本轮通过。

## 6. pending 与限额（不猜测填通过）

| 目标 | 状态 | 原因 |
| --- | --- | --- |
| android | pending | 本工作流不构建也不驱动 Android 宿主。真实入口（content VIEW / SEND / SEND_MULTIPLE / ACTION_OPEN_DOCUMENT + 真 DocumentsProvider）属于 J04 producer，需要它自己的 Gradle 与模拟器轮；用 Android 工具链跑一次模块导入不构成 host 证据。 |
| iphone | pending | 本工作流不构建 iOS 应用，模拟器的 document-open / 分享面板交接一次都没执行。属于 Apple import-mapping producer，Apple 宿主收口由集成 owner 保留。 |
| ipad | pending | 同 iphone。 |

另外未验证/不授予：真机、读屏、USB 线缆、性能预算、系统文件选择器的原生点选、拖拽手势本身
（本包走的是剪贴板/粘贴板交接路由）、云盘 transport 的产品路径（属 cloud-import producer）。
本包**不计入**旧 1710 真实语料计数；不提交任何新二进制夹具，下载副本/改名副本/截断/垃圾/空文件
全部在 CI 内生成。

## 7. 复现

```text
python3 tests/reader_final_s06/matrix.py selftest --spec tests/reader_final_s06/matrix_spec.json --output build/s06-guard
python3 tests/reader_final_s06/matrix.py compile  --spec tests/reader_final_s06/matrix_spec.json \
  --evidence build/s06-evidence --output build/s06-report
```

`compile` 默认从 `GITHUB_SHA/GITHUB_RUN_ID/GITHUB_RUN_ATTEMPT` 取身份；guard 作业还会跑 12 例
编译器协议（10 个必须被拒 + 1 个必须被接受，本轮 12/12 通过），包括「模块层不能填 host 单元」
（3 目标 × 5 host 单元 = 15 个 blocked）。
