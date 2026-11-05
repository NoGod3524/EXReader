# S06 六目标导入入口回归矩阵

实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。本包只新增
`tests/reader_final_s06/`、`.github/workflows/reader-final-s06.yml`、`docs/reader-final-s06/`
与根 `HANDOFF-RESULT.md`；宿主、SDK、原 tests、原 workflow、预算与保护树一律只读。

## 1. 这是什么

一个**统一入口矩阵**：把「用户实际怎么把一本书交给阅读器」拆成五条真实入口动作，加上两条支撑身份、
取消与重开的单元，逐目标逐项给出**同一 run、同一 source、同一二进制**的结果。

矩阵不是新宿主。它复用三个已安装的公开包，并把它们的真实动作串成一条链：

| 层 | 复用对象 | 作用 |
| --- | --- | --- |
| SDK | 冻结 3.40 书库（`EXReader::exr_library`） | 原件字节、去重、进度/标注、重开 |
| 导入入口 | `extras/sideload`（`exr_sideload_import_file` / `_import_source` / `export_original`） | 宿主唯一导入入口：限额、取消、精确去重、私有原件导出 |
| 系统交接 | `extras/desktop-drop`（`*_clipboard_request` / `request_from_pasteboard`） | 真实操作系统剪贴板/粘贴板的文件交接 |

探针 `s06-matrix-probe` 只链接**安装后的**这三个包，不进入任何私有头文件，也不改它们的一行代码。

## 2. 矩阵

七个单元 × 六目标。每个单元要求的最低证据层写在 spec 里，由编译器强制执行。

| 单元 | 要求的层 | 真实动作 |
| --- | --- | --- |
| `local_file` | host | 从宿主私有目录的稳定路径发起导入；UTF-8/空格路径；借用只读 source 路由；原件逐字节回读 |
| `system_open_share` | host | 探针自己写真实剪贴板/粘贴板（CF_HDROP / text/uri-list / NSPasteboard file URL），经安装的适配器读回，再导入被交接的那条路径；目录不当成书；缺失路径被拒；多条目 |
| `cloud_download_to_sideload` | host | 从固定 commit 经 HTTPS 下载原件（Actions 内 `curl`），下载字节与仓库 fixture 逐字节相同后，把**下载副本**送进 sideload；同一原件已存在时必须落到同一本书 |
| `duplicate_same_original` | host | 同路径重投、改名副本重投都 `created=0` 且 id 不变；标题/进度/标注保留；重投时取消不伤旧书 |
| `bad_file` | host | 截断、随机垃圾、0 字节、不存在四种坏输入逐项显式拒绝，零新增行，旧原件仍可读 |
| `nine_formats_original_identity` | module | TXT/HTML/FB2/EPUB/DOCX/RTF/MOBI/PDF/CBZ 九格式各一次导入 + 原件逐字节回读 + 二次导入去重 + 私有原件导出，最后关库重开 |
| `entry_cancel_and_reopen` | module | 提交前取消（memory 与 stream 两条路由）零行；提交后结果不因取消被删；导出第二次不覆盖既有文件；关库重开后已提交书与其原件仍在 |

目标：`windows`（windows-2022）、`linux`（ubuntu-22.04 + GTK3 + Xvfb）、`macos`（macos-15）
本工作流实跑；`android`、`iphone`、`ipad` 在 spec 里显式 `expects_evidence: false`，
每个单元都记 `pending` 并带上具体原因——见第 5 节。

## 3. 证据绑定与拒绝规则

`tests/reader_final_s06/matrix.py` 是唯一裁判，规则写在代码里而不是散文里：

- 每个单元列出**必须存在且必须 pass** 的 case 名；缺一个就是该单元 fail，不降级成 skip。
- 证据目录必须带 `identity.json`：source SHA、run id、attempt、platform、**探针二进制 sha256 与字节数**、层。
  任一项与本次 run 不符即拒绝；探针二进制被重新哈希并与记录比对。
- 证据流声明**实际跑到的层**。`module` 层永远不能填 `host` 单元，只能记 `blocked`。
  这就是「不能用模块通过填 host 通过」的可执行形式。
- 重复 case 名、截断 JSON、缺 `__summary` 或计数不一致、非零退出码、空流，全部算损坏而不是通过。
- 本工作流声明可测却**没有产出证据**的目标直接让整轮失败，不会悄悄变成 pending。
- `matrix.py selftest` 在 guard 作业里跑 10 个反例（模块填 host、异 source、异 run、异 attempt、
  缺 case、失败 case、重复 case、摘要不符、空流、非零退出、可测目标无证据）与 1 个正例，全部必须按预期被拒/被接受。

## 4. 与旧记录的关系

- 不计入旧 1710 真实语料计数；本次用仓库既有 fixture，夹具副本（下载副本、改名副本、截断/垃圾/空文件）
  全部在 CI 内生成，不提交任何新二进制。
- 不合并其它功能分支，不消费其它 producer 的旧工件；本页结果全部来自本工作流自己的 run/attempt。
- 不授予：真机、读屏、USB/线缆、性能预算、系统文件选择器的原生点选、拖拽手势本身、云盘 transport 产品路径、
  Apple 宿主收口。分别仍为独立跟踪项。

## 5. 未测（pending）与原因

| 目标 | 状态 | 原因 |
| --- | --- | --- |
| android | pending | 本工作流不构建也不驱动 Android 宿主。真实入口（content VIEW / SEND / SEND_MULTIPLE / ACTION_OPEN_DOCUMENT + 真 DocumentsProvider）属于 J04 producer，需要它自己的 Gradle 与模拟器轮；用 Android 工具链跑一次模块导入并不构成 host 证据，因此不填。 |
| iphone | pending | 本工作流不构建 iOS 应用，模拟器的 document-open / 分享面板交接一次都没执行。该轮属于 Apple import-mapping producer，Apple 宿主收口由集成 owner 保留。 |
| ipad | pending | 同 iphone。 |

## 6. 复现

```text
python3 tests/reader_final_s06/matrix.py selftest \
  --spec tests/reader_final_s06/matrix_spec.json --output build/s06-guard

python3 tests/reader_final_s06/matrix.py compile \
  --spec tests/reader_final_s06/matrix_spec.json \
  --evidence build/s06-evidence --output build/s06-report
```

`compile` 从 `GITHUB_SHA`/`GITHUB_RUN_ID`/`GITHUB_RUN_ATTEMPT`（或同名参数）取本次身份，
把每个平台的证据目录（`<platform>/identity.json`、`probe.jsonl`、`probe.exit`、`probe/s06-matrix-probe`）
编译成 `report.json`。`normalize.py` 只做一件事：按 `identity.json` 里的 platform 把下载下来的证据树
摆放整齐，不改变任何内容。
