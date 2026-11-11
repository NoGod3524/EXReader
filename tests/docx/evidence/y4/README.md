# Y4 编辑器总集成验收

初始基底为 #124 `6cb452da`，依次合入 X1 `33e9ba27`、X6 `082dca1f`；验收期间 #124 并入 main 后，又同步其最新基底 `9841d30b`。最终可执行源码在 `c04560b7`，以下数字均来自同步后的完整复验。[PR #125](https://github.com/NoGod3524/EXReader/pull/125) 以 #124 为目标。交付时 #124 又推进至 `139e0ad5`，该次变化仅涉及 CI 治理；已逐树核对 src/include/cmake/tests/CMakeLists 与本轮验收基底完全相同，合并模拟无冲突。本分支未改动 .github。

| 验收 | 结果 |
| --- | --- |
| 构建 | Ninja `all` 完成，最终 `no work to do`；全部已配置组件、工具、测试、fuzz、公共头目标通过 |
| CTest | **321/321，0 失败，1026.94 秒，-j2**，无排除项；包含 `sdk-release` |
| 新增测试 | **28 组**：X1 13、X6 14、Y4 1；Y4 组内包含 X5 六夹具及一个组合工作流 |
| 对齐 281 基线 | 281 + 4 组新并入 #124 的固定版式基线测试 + 28 新组 + 7 组额外启用的已有 fuzz + 1 项原先排除的发行测试 = 321 |
| 独立 #124 对照 → 编辑桥 | **5/18 → 18/18**；文本、图片哈希与 SDK 重读一致 |
| 真书 | **19/19，11,318 页，8,648,571 字形**；页数变化 0、逐页像素哈希变化 0 |
| 分层 | 124 对象，新增/遗留逆向符号引用均为 0，逆向 include 为 0 |

首次基底上 317/317 通过的记录保留于 `abaf35b2`。同步新基底后，高并发与渲染同时运行曾触发 corpus-triage 原有 60 秒子进程超时；停止该次尝试并保留 [日志](resource-contention.txt)，待渲染结束后以 -j2 完整复验，321/321 通过，未改断言或超时设置。

构建环境：Windows x64、GCC 16.2、Release、Ninja，开启 fuzz；PDF、crypto、JPX、ICC、audio、library、text-index 开启；可选 WebP/TIFF/AVIF 关闭，PNG/JPEG 开启。SDK smoke 使用实际 MSVC 导入库并执行原 Windows README 的编译、运行及 PGM 检查；发布脚本未改。

## 端到端逐步断言

组合夹具由本仓库测试函数生成，全部文字和 PNG 为原创。X5 六份夹具另按原 manifest 核对 SHA-256、结构、无修改往返及重开；`generate.py --check` 可逐字节复现六夹具和 manifest。

| 步骤 | 断言结果 |
| --- | --- |
| 打开并断言结构 | PASS：XML 15 段、1 表（3 行 × 2 列）、1 图、1 脚注、2 节；模型顶层 9 段 |
| 插入 5 段 | PASS：模型顶层 9 → 14 段，重开后五段文字均存在 |
| 修改 3 段属性 | PASS：三段对齐值 1/2/3，左缩进 900/1000/1100 twips，重开一致 |
| 拆 1 段 | PASS：模型顶层 14 → 15，重开后两个片段文字正确 |
| 删 1 段 | PASS：模型顶层 15 → 14，重开后被删段不存在 |
| 表格加 1 行 | PASS：3 → 4 行、仍为 2 列；原三行文本不变，新行 A/B 单元格文字正确 |
| 插入 PNG | PASS：原有 1 图 → 2 图，新增 PNG 原始字节相同，尺寸 72 × 48 pt |
| 保存并重开 | PASS：XML 15 → 23 段（含新增两单元格段和图片段），表数 1、脚注 1、节数 2；四边距不变 |
| 格式及内容保留 | PASS：Times New Roman 12 pt，行距 480/auto；未修改段缩进 720/120/360，修改段保留右/首行缩进和行距；注释、样式、页眉、原媒体等非目标 OPC 部件逐字节保留；再次写出全部 package parts 相同 |

[e2e.json](e2e.json) 保存每步结果、六夹具结构、格式值及源/输出哈希。段落计数包含单元格和图片容器段，因此与模型顶层段数分别记录。

## #117 六指标 × 三文档

对照 DLL 从最新 #124 `9841d30b` 原始 `edit.h`、`docx_edit.c`、`docx_reflow.c`、`pager.c` 编译；其余复用对象逐个核对源码与 #124 相同，并链接同一依赖。使用 [build_editor_baseline.py](../../build_editor_baseline.py) 构建；[baseline-build.json](baseline-build.json) 记录来源及 DLL 哈希。

| 编辑桥无修改往返 | Minitab | SOCI | UN |
| --- | --- | --- | --- |
| 段落 | 336 → 336 | 117 → 117 | 209 → 209 |
| 字符 | 13,865 → 13,865 | 5,555 → 5,555 | 71,205 → 71,205 |
| 表格 | 10 → 10 | 2 → 2 | 2 → 2 |
| 图片 | 17 → 17 | 0 → 0 | 0 → 0 |
| 脚注 | 0 → 0 | 0 → 0 | 5 → 5 |
| 节及四边距 | 1 节，一致 | 5 节，一致 | 1 节，一致 |

本次独立实测 #124 为 5/18；旧 #117 留存证据为 4/18，未用旧数字替代实测。通过口径是六项结构指标相等；同时额外检查正文/注释文本与图片哈希、SDK 重读和格式校验结果相对源文不变。原文不必符合新建文档的格式模板。

三份真文档另通过 X1 的插入 5 段、修改 3 段、保存重开、撤销重做，以及 X6 的加行、单元格/宽度编辑、删回临时行、重开和撤销重做；X6 编辑前后均为 18/18。

## 冲突与文件取并集记录

| 文件 | 合并结果 |
| --- | --- |
| `src/docx_edit.c` | 自动合并保留 X6 表/行/单元格/图片的验证、深拷贝、ID 与历史，以及 X1 opaque 块和节属性处理。 |
| `src/docx_edit_io.c` | 保留较新 X1 的节边界、隐式节、局部命名空间、页眉页脚引用及 OOXML 顺序修复，并采用 X6 共享 XML 函数名、表格与图片 IO；原有两套测试均保留。 |
| `include/exr/edit.h` | 保留 X1 桥与模板语义、X6 结构和全部 API；桥声明由越界的 `formats.h` 调整至本头。 |
| `tools/layers.json` | 两套源文件和内部头登记均保留，删除重复的 edit.h 键；模型内部头命名为 `docx_edit_model_internal.h`。 |
| `cmake/modules.cmake` | #124 已按 layers 清单发现新增源文件，无冲突且无需修改。 |
| `CMakeLists.txt` | 保留原模型/重排测试，并合并 13 + 14 + 1 组新增测试登记。 |
| `OUT.txt` | 保留 #124 原记录及全部 Y4 逐步追加记录；`OUT2.txt`、`OUT3.txt` 保留分支原报告；追入最新 #124 时仅 OUT.txt 冲突，继续保留双方全部记录。 |
| `tools/docx/README.md`、`tools/docx/roundtrip.py` | 冲突均保留 #124 版本，以遵守边界；新的 editable 对比放在 `tests/docx/`。 |
| 其它越界导入文件 | X1 发布脚本、`formats.h`、历史 evidence 与 X6 docs 均恢复为 #124，实际功能在允许范围内落地。 |

同步 #124 所带固定版式源码、文档与证据均为上游原样继承，不属于本 PR 的编辑器增量。`src/export_text.c` 与验收基底及当前 #124 相同，`.github/` 相对任务起点 `6cb452da` 未改动；X1、X6 和验收基底 `9841d30b` 均为当前分支祖先，合入当前 #124 分支无冲突。详见 [scope.json](scope.json)。

## 证据与复现

[ctest.txt](ctest.txt)、[build.txt](build.txt)、[layers.txt](layers.txt)、[sdk-release.json](sdk-release.json)、[roundtrip.json](roundtrip.json)、[paragraph-edits.json](paragraph-edits.json)、[table-edits.json](table-edits.json)、[realbooks.diff.json](realbooks.diff.json)、[逐页哈希压缩数据](realbooks.json.gz)、[summary.json](summary.json)。真书使用仓库冻结基线 `evidence/w1/realbooks-baseline.json.gz`；内容指纹为 `8e51f8a0ad679f1fab702a96aed50dd02ad32d4d3624f0e30b1234ff20cd5434`。

```powershell
cmake -S . -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_FUZZ=ON -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF
cmake --build build/native -j 6
# MinGW 下用已安装 MSVC 的 lib.exe 生成与实际 DLL 同名的导入库，供原 SDK README 使用：
New-Item -ItemType Directory -Force build/native/Release
& 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/HostX64/x64/lib.exe' /nologo /machine:x64 /name:libexreader.dll /def:build/native/exreader.def /out:build/native/Release/exreader.lib
ctest --test-dir build/native --output-on-failure -j 2
python tests/fixtures/docx-edit/generate.py --check
python tests/test_docx_editor_e2e.py --library build/native/libexreader.dll --output build/y4/e2e
python tests/docx/build_editor_baseline.py build/native
python tests/docx/check_editor_roundtrip.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --baseline-library build/native/editor-baseline/libexreader.dll --output build/y4/roundtrip
python tests/docx/check_edit_bridge.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/y4/real-paragraph-edits
python tests/docx/check_table_image.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/y4/real-table-edits
python tools/check_layers.py build/native
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/native/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf --layout tools/regress/layout.json --workers 2 --source-revision c04560b7 --baseline build/y4/books-baseline.json --output build/y4/realbooks.json
```

依赖可用现有 `FETCHCONTENT_SOURCE_DIR_*` 缓存；三份私人 DOCX 按 `tests/docx/corpus.json` 的路径与哈希放入忽略的 `build/docx-inputs`；真书基线 JSON 由上述 gzip 解压到 `build/y4/books-baseline.json`。测试生成的 DOCX 均留在忽略的 build 下。
