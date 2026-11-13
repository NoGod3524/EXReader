# PPTX M1 验收记录

基线：`54436bfa`。实现文件 `src/pptx.c` 共 416 行，15 个函数。
`EXR_PPTX=11` 追加在 `EXR_PPT=10` 之后；原枚举数值保持不变。

## 实现结构与函数清单

| 部分 | 函数 | 职责 |
| --- | --- | --- |
| 生命周期 | `release` | 释放 ZIP、输入字节、页目录与 part 路径 |
| XML 节点 | `named`, `root`, `child`, `relationship_id` | 命名空间匹配、直接子节点与 r:id 读取，兼容 Transitional/Strict PresentationML |
| 容器 | `check_archive`, `xml_read` | 全成员大小预检、元数据预算、解压与现有 XML 树解析器接入 |
| 关系 | `compare_relationships`, `read_relationships`, `find_relationship` | 关系表读取、排序、重复 ID 校验与二分查找 |
| 骨架 | `dimension`, `read_presentation` | EMU 转 pt、缺省尺寸、按 sldIdLst 建立页序、跳过缺失引用 |
| 固定版式 | `draw`, `create_fixed`, `exr_pptx_open_owned` | 空绘制、几何与 provider 注册、打开流程及失败清理 |

`src/formats.c` 新增私有 `exr_zip_format`，按 `[Content_Types].xml`
中的 PresentationML 主文档 MIME 识别 PPTX。固定版式文件入口支持内容探测和
`.pptx`/`.PPTX` 后缀；内存入口支持 `EXR_PPTX`。

每个有效引用保留 `pptx_slide { part_path, index }`，其中 index 为跳过前的
原始零基页序。固定页几何采用 pt、左上原点、y 向下、unit_scale=1。
`exr_fixed_create` 支持 page_count=0、pages=NULL，接受空演示文稿。
M1 的 draw 回调不输出任何形状或文本，背景由固定版式渲染管线提供。

## 验收 ①②③④：夹具、页数、尺寸与渲染

生成脚本：`tests/fixtures/pptx-skeleton/generate.py`，使用 python-pptx 1.0.2。
脚本统一 ZIP 时间戳、成员顺序、平台与权限，并将重新读取后的页数和 EMU 尺寸
写入 `manifest.json`。生成与 `--check` 字节复现检查均 exit 0。

| 夹具 | 引擎页数 | python-pptx 页数 | 页尺寸 pt |
| --- | ---: | ---: | --- |
| empty.pptx，空演示文稿 | 0 | 0 | 无页面；声明尺寸 720×540 |
| title.pptx，纯标题 | 1 | 1 | 720×540 |
| layouts.pptx，五种版式 | 5 | 5 | 720×540 |
| wide.pptx，16:9 | 1 | 1 | 960×540 |
| standard.pptx，4:3 | 1 | 1 | 720×540 |
| twenty.pptx，二十页 | 20 | 20 | 720×540 |

16:9 的 EMU 尺寸为 12192000×6858000；4:3 为 9144000×6858000。
每份均通过文件与内存两种打开入口。六份基础夹具共 28 页，两种入口合计
56 次 `exr_fixed_render` 成功；逐字节验证 RGBA 位图为全白，尺寸与几何一致。
0 页与普通文档的越界 render 均返回 EXR_ARGUMENT，输出位图为空。

## 验收 ⑤：坏样本与容错原文

以下结果在文件入口和内存入口一致，失败时输出文档为 NULL。

| 样本 | 状态 | exr_error.message 原文 |
| --- | --- | --- |
| 截断 PPTX | EXR_FORMAT (5) | `Invalid or truncated PPTX/ZIP container` |
| 缺 presentation.xml | EXR_FORMAT (5) | `PPTX part missing: ppt/presentation.xml` |
| presentation.xml 损坏 | EXR_FORMAT (5) | `Invalid PPTX XML part: ppt/presentation.xml` |
| 缺内容类型 | EXR_FORMAT (5) | `PPTX presentation content type missing in [Content_Types].xml` |
| 重复关系 ID | EXR_FORMAT (5) | `Duplicate PPTX relationship ID: rId2` |
| 内容类型成员大于 128 MiB | EXR_LIMIT (6) | `ZIP member exceeds 128 MiB: [Content_Types].xml` |
| 幻灯片成员大于 128 MiB | EXR_LIMIT (6) | `ZIP member exceeds 128 MiB: ppt/slides/slide1.xml` |

五页文档缺 slide2.xml 时保留四页并维持其余页序，返回 EXR_OK (0)，警告原文：

```text
PPTX warning: skipped 1 slide reference(s) with missing or invalid parts
```

缺全部关系时返回 0 页并报告 skipped 5；缺两张 slide 时报告 skipped 2。
缺失、零值和非法尺寸均验证回退到 720×540 pt。反向页序、绝对 part 路径、
无效外部目标、大小写后缀以及 `.bin` 后缀内容探测均已通过。

## 验收 ⑥⑦：CTest

新增 12 组，全部通过：

```text
native-pptx-empty
native-pptx-title
native-pptx-layouts
native-pptx-wide
native-pptx-standard
native-pptx-twenty
native-pptx-errors
native-pptx-defaults
native-pptx-missing
native-pptx-order
native-pptx-detection
native-pptx-limit
```

专项命令及结果：

```text
ctest --test-dir build/pptx-m1 -R ^native-pptx- -V --output-on-failure
100% tests passed out of 12
Total Test time (real) = 26.79 sec
exit 0
```

全量命令及结果（417 组既有测试 + 12 组新增测试）：

```text
ctest --test-dir build/pptx-m1 -E "^(sdk-release|sdk-doc-coverage)$" --output-on-failure -j 2 --output-junit ctest-results.xml
100% tests passed out of 429
Total Test time (real) = 418.90 sec
exit 0
```

已登记到 `tests/fixtures/docx-real/codex/register.cmake` 的 Linux/GNU ASan
ctypes 预载正则。测试本身仅依赖 Python 标准库，生成夹具才需要 python-pptx。

完整本地日志：`build/pptx-m1/pptx-ctest.log`、`ctest-all.log` 和
`ctest-results.xml`；构建日志为仓库根目录的 `build-pptx-build.log`。

## 验收 ⑧与约束检查

- Release 全功能构建 exit 0，PPTX 编译采用 `-Wall -Wextra -Wpedantic -Werror`。
- `check_sdk_docs.py --binary build/pptx-m1/libexreader.dll` exit 0：482/482 公开函数，覆盖率 100%，DLL 缺失/额外导出均为空。现有固定版式 API 的六标签文档已更新。
- `check_layers.py build/pptx-m1` exit 0：129 个对象，0 个新逆向引用，0 个逆向 include。新源文件按当前 CMake 清单机制登记在 `tools/layers.json`；没有新增头文件。
- 共用 `C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1 -Worktree <本工作树>` 检查通过；当前仓库的 ops 目录未包含该脚本。
- `src/docx.c`、`tests/check_reading_release.py`、`tools/version_literal_exceptions.json` 未修改。全程使用命令行，无 GUI/SendInput。

## M2 可复用接口与需要延伸的位置

1. **页与容器上下文**：`pptx_document.zip/data/slides` 已保留 ZIP 和有序 part 路径。
   M2 可在 draw 时读取 `slides[page].part_path`，原始 index 可用于诊断。
2. **按 part 解析 XML**：复用 `xml_read` 与 `exr_xml_memory_tree`。M2 需要读取
   slide 的 `p:cSld/p:spTree`；目前 expanded 是打开阶段累计预算，新增页绘制时
   应采用每次操作的预算，避免重复绘制永久累加。
3. **关系与继承链**：复用 `read_relationships`、`find_relationship` 和
   `exr_resolve_path`；添加每张 slide 的 `_rels` 路径及 layout/master/theme
   关系遍历。关系结构中的字符串借用 XML 树，树释放前必须完成使用或复制。
4. **形状绘制入口**：填充现有 `draw(context, page, matrix, sink, control, error)`。
   EMU 坐标除以 12700 后通过 `exr_path_segment`、`exr_draw_style` 和 sink 的
   path/clip/state 输出；继续使用调用方传入的 matrix 与 control。
5. **固定版式管线**：复用 `exr_fixed_page.geometry`、`exr_fixed_create`、
   `exr_fixed_draw_fn`、`exr_fixed_render`。需要扩展图形能力时可接现有可选
   `draw_ex`；白底、视口、裁剪、位图所有权和取消流程已有实现。
