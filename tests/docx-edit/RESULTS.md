# X5 编辑路径回归验收

2026-11-10，Windows x64 / MinGW Release / Python 3.14.7，无 GUI。
X5 **20/20 PASS**，18 个正向用例均完成打开、编辑、保存、重开及 13 次撤销。
每个夹具的 18 项编辑指标全部通过，共 **108/108**；其中直接复用 #117
`roundtrip.metrics()` 的六项指标为 **36/36**。

本分支基于 `aaf8aecc`，尚未合入编辑桥和 #117。本次联跑使用实际编译的
X1 工作树 SDK 和未经修改的 #117 校验器。

| 依赖 | 工作树提交 | 本次使用位置 |
| --- | --- | --- |
| X1 编辑桥 | `1e6f1e294757829c2ee387324e4f32ccf04b530a` | `../EXReader-x1-bridge-20261110/build/native/libexreader.dll` |
| #117 校验器 | `51c6d5cff01cd7b84cca15d29d27864f30d0b5c6` | `../EXReader-dxverify-20261110/tools/docx/` |

库、校验器源文件、夹具、编辑产物和报告的 SHA256，以及每项指标的期望值和
实测值均保存在 [evidence/summary.json](evidence/summary.json)。

六个夹具全部由 [generate.py](../fixtures/docx-edit/generate.py) 自造，未使用外部
文档、模板或图片。生成器只用 Python 标准库，固定 ZIP 元数据，逐字节再生成
检查已通过。下面是磁盘上的实际大小，均小于 50,000 字节。

| 夹具 | 字节 | 原始结构 | 编辑指标 |
| --- | ---: | --- | ---: |
| [plain.docx](../fixtures/docx-edit/plain.docx) | 3,491 | 3 段正文 | 18/18 PASS |
| [heading.docx](../fixtures/docx-edit/heading.docx) | 3,525 | Heading1 标题及正文，共 3 段 | 18/18 PASS |
| [table.docx](../fixtures/docx-edit/table.docx) | 6,092 | 3 段正文、1 个 3×3 表格 | 18/18 PASS |
| [image.docx](../fixtures/docx-edit/image.docx) | 4,443 | 3 段正文、1 张内嵌 PNG | 18/18 PASS |
| [notes.docx](../fixtures/docx-edit/notes.docx) | 5,190 | 3 段正文、1 条脚注、1 条尾注 | 18/18 PASS |
| [sections.docx](../fixtures/docx-edit/sections.docx) | 4,582 | 3 段正文、2 节不同页边距、关联页眉与 PAGE 域 | 18/18 PASS |

以下 20 个 ctest 用例全部通过。正向用例分别报告内容、结构、属性；每例均执行
完整编辑链路及撤销检查，表格单元格内段落也计入独立 XML 段落统计。

```text
PASS native-docx-edit-fixtures
PASS native-docx-edit-e2e-plain-content
PASS native-docx-edit-e2e-plain-structure
PASS native-docx-edit-e2e-plain-properties
PASS native-docx-edit-e2e-heading-content
PASS native-docx-edit-e2e-heading-structure
PASS native-docx-edit-e2e-heading-properties
PASS native-docx-edit-e2e-table-content
PASS native-docx-edit-e2e-table-structure
PASS native-docx-edit-e2e-table-properties
PASS native-docx-edit-e2e-image-content
PASS native-docx-edit-e2e-image-structure
PASS native-docx-edit-e2e-image-properties
PASS native-docx-edit-e2e-notes-content
PASS native-docx-edit-e2e-notes-structure
PASS native-docx-edit-e2e-notes-properties
PASS native-docx-edit-e2e-sections-content
PASS native-docx-edit-e2e-sections-structure
PASS native-docx-edit-e2e-sections-properties
PASS native-docx-edit-e2e-table-negative
```

编辑批次插入 5 段，修改 3 个原段落的字体、字号、行距及缩进，拆分 1 段，删除
1 段，最终净增 5 段。拆分位置在中文之后，以 UTF-8 字节边界传给公开 API。
保存重开后同时检查引擎属性和独立 XML。撤销 13 条命令后，主文档 XML 树与
原夹具等价，其余 OPC 部件逐字节相同；再重开保存仍等价。

故意失败使用两种入口，均已实跑：自动负向用例破坏实际引擎产物；另一次在
测试外独立解包 `table-structure/edited.docx`，从 `word/document.xml` 手工删掉
唯一的 `w:tbl` 后重新打包，再用 `--check-output` 检查该文件。两次子用例
退出码都是 **1**，均明确报告：

```text
FAIL table/structure: table/structure 保存重开: 表格数 1→0; 表格内容元素数 1→0
```

[手工删表原始诊断](evidence/manual-table-negative.txt)和两次负向报告均保存在
验收证据中。自动负向用例只有在子用例确实失败且包含“表格数 1→0”时才通过。

#117 的固定排版检查与结构指标分别保留结果。它的 `verify()` 共 **14 项**，
要求 Times New Roman、12pt、双倍行距、统一一英寸页边距和 PAGE 页眉。本任务
有意改变前三种属性，且要求不同节页边距；前五个最小夹具也没有页眉。因此，
这些编辑产物没有全部通过该固定排版规则，原始 FAIL 均保留：

| 编辑产物 | 固定排版 PASS | FAIL | WARN | 六项结构指标 | X5 扩展指标 |
| --- | ---: | ---: | ---: | ---: | ---: |
| plain | 8 | 4 | 2 | 6/6 | 18/18 |
| heading | 8 | 4 | 2 | 6/6 | 18/18 |
| table | 8 | 4 | 2 | 6/6 | 18/18 |
| image | 8 | 4 | 2 | 6/6 | 18/18 |
| notes | 8 | 4 | 2 | 6/6 | 18/18 |
| sections | 10 | 4 | 0 | 6/6 | 18/18 |
| 合计 | 50 | 24 | 10 | 36/36 | 108/108 |

前三项固定失败为 `double_spacing`、`font_times_new_roman`、`font_size_12pt`。
前五份的第四项为 `header_page_field`；sections 的第四项为 `one_inch_margins`。
测试要求完整状态表符合预期，同时逐项验证修改后的真实属性和保留的结构。
18 项编辑指标的定义见 [README.md](README.md)，六项原有指标按本次编辑批次
计算段落及字符增量，其余四项要求与原夹具相同。

本地关闭 fuzz 附加测试后，既有清单实际为 **256** 个：所给基线 255 加已存在的
`simplified-observer`（由 `cf8c20792` 引入，早于 X5）。X5 新增 **20** 个，
因此本次实际总数为 **256 → 276**；相对于所给 255，差值是 21，其中仅 20 个
来自本次任务。[完整 ctest 输出](evidence/ctest-full.txt)为 **275/276 PASS**，
唯一失败为既有 `sdk-release`：MinGW 包包含 `libexreader.dll.a`，但 README
示例使用 MSVC 查找 `lib/exreader.lib`，报 `LNK1181`。

复验命令（本机预合入依赖位置）：

```powershell
cmake --build ../EXReader-x1-bridge-20261110/build/native --target exreader -j 4
cmake -S . -B build/native -DEXR_BUILD_FUZZ=OFF -DEXR_DOCX_EDIT_TEST_LIBRARY=C:/Users/Oscar/Documents/Codex/EXReader-x1-bridge-20261110/build/native/libexreader.dll -DEXR_DOCX_EDIT_VALIDATOR_DIR=C:/Users/Oscar/Documents/Codex/EXReader-dxverify-20261110/tools/docx
cmake --build build/native -j 4
ctest --test-dir build/native -L docx-edit --output-on-failure -j 4
ctest --test-dir build/native --output-on-failure -j 4
python tests/docx-edit/run.py --library ../EXReader-x1-bridge-20261110/build/native/libexreader.dll --validator-dir ../EXReader-dxverify-20261110/tools/docx --fixture table --case structure --check-output build/hand-modified-table.docx --output build/manual-table-negative
```

依赖合入后清空 `EXR_DOCX_EDIT_TEST_LIBRARY`，将 `EXR_DOCX_EDIT_VALIDATOR_DIR`
设为本仓库 `tools/docx`，后续 ctest 即验证当前构建的 SDK。默认值已经如此设置；
缺失 API 或校验器会使测试失败。
