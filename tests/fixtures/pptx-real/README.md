# PPTX M6 逐页语料

本目录包含 **12 份有效演示文稿，共 31 页，以及 3 份坏文件**。每件都有独立
`manifest.json`；[总 manifest](manifest.json) 汇总所有 15 件，使用相对于本目录的
文件路径，保留下载件的来源、许可、固定上游提交及 SHA-256。

11 份有效生成件由 `python-pptx` 创建完整的 Office OPC 包，包含主题、母版、版式、
关系及内容类型。下载件为未修改的上游 PowerPoint 文件，原始应用元数据为
Microsoft Macintosh PowerPoint 14.0000。它来自公开的 `python-pptx` 集成测试库；
来源性质及原始字节均保留。

| 文件 | 页数 | 特性 | 来源 | 许可 |
|---|---:|---|---|---|
| [title/title.pptx](title/title.pptx) | 1 | 纯标题、无填充文本框、16:9 | 生成 | MIT |
| [bullets/bullets.pptx](bullets/bullets.pptx) | 1 | 项目符号、0/1/2 三级、正文、16:9 | 生成 | MIT |
| [image-text/image-text.pptx](image-text/image-text.pptx) | 1 | 原创 PNG、图片拉伸、文字混排 | 生成 | MIT |
| [merged-table/merged-table.pptx](merged-table/merged-table.pptx) | 1 | 表格、横纵合并、显式填充与边框、单元格文本 | 生成 | MIT |
| [gradient-alpha/gradient-alpha.pptx](gradient-alpha/gradient-alpha.pptx) | 1 | 真正的 `p:bg` 渐变背景、形状渐变、半透明、矩形/椭圆/圆角矩形 | 生成 | MIT |
| [theme-accents/theme-accents.pptx](theme-accents/theme-accents.pptx) | 1 | `schemeClr`、accent1–6、文字 | 生成 | MIT |
| [chinese/chinese.pptx](chinese/chinese.pptx) | 1 | 中文标题、正文、表格 | 生成 | MIT |
| [standard-4x3/standard-4x3.pptx](standard-4x3/standard-4x3.pptx) | 1 | 4:3、文字、矩形、椭圆 | 生成 | MIT |
| [wide-16x9/wide-16x9.pptx](wide-16x9/wide-16x9.pptx) | 1 | 16:9、文字、矩形、椭圆 | 生成 | MIT |
| [nested-groups/nested-groups.pptx](nested-groups/nested-groups.pptx) | 1 | 两层组、组缩放、椭圆、三角形、圆角矩形 | 生成 | MIT |
| [twenty/twenty.pptx](twenty/twenty.pptx) | 20 | 综合页、表格、嵌套组、圆/三角形/直线、图片平铺、形状图片填充、水平/垂直翻转、90° 旋转、性能标记 | 生成 | MIT |
| [upstream-font-color/upstream-font-color.pptx](upstream-font-color/upstream-font-color.pptx) | 1 | 原始 PowerPoint 包、主题文本颜色、accent1/4、`lumMod`/`lumOff` | [下载：固定提交原件](https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/font-color.pptx) | [MIT](https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE) |
| [bad-truncated/bad-truncated.pptx](bad-truncated/bad-truncated.pptx) | 0 | 截断 ZIP；期望 `5 / EXR_FORMAT` | 生成 | MIT |
| [bad-missing-part/bad-missing-part.pptx](bad-missing-part/bad-missing-part.pptx) | 0 | 缺少 `ppt/presentation.xml`；期望 `5 / EXR_FORMAT` | 生成 | MIT |
| [bad-invalid-xml/bad-invalid-xml.pptx](bad-invalid-xml/bad-invalid-xml.pptx) | 0 | 幻灯片 XML 结束标签不匹配；期望 `5 / EXR_FORMAT` | 生成 | MIT |

生成件及原创图片依照仓库的 [MIT LICENSE](../../../LICENSE) 发布；生成源为
[generate.py](generate.py)。下载件的 [独立来源说明](upstream-font-color/README.md)、
[上游许可原文](upstream-font-color/LICENSE) 和
[上游分发清单](upstream-font-color/UPSTREAM-MANIFEST.in) 一并入库。

## 生成与确定性检查

从仓库根目录运行，生成环境为 Python 3.14、`python-pptx 1.0.2` 和 `Pillow 12.3.0`：

```powershell
python -m pip install python-pptx==1.0.2 Pillow==12.3.0
python tests/fixtures/pptx-real/generate.py
python tests/fixtures/pptx-real/generate.py --check
```

`--check` 重新构造 11 份有效件及 3 份坏文件，并逐字节核对已入库文件与子 manifest；
随后核对总 manifest 是否仍等于所有子 manifest 的汇总。它不联网，不改写下载件。
生成模式也只读取下载件的 manifest 以更新索引，不改写下载件、来源或许可。

跨平台字节一致性采用：固定文档创建/修改时间和作者字段；ZIP 成员按路径排序；
固定时间戳、权限及创建系统；所有生成件使用 `ZIP_STORED`；原创 PNG 使用
`compress_level=0`。固定依赖版本后，`--check` 可直接检查宿主生成的字节是否一致。
下载原件保留其原始 ZIP 压缩方式，完整性由子 manifest 中的 SHA-256 校验。

## 运行逐页矩阵

完成含共享库与测试的 Release 构建后运行：

```powershell
python tests/pptx_real_matrix.py --library build/pptx-m6/libexreader.dll --output build/pptx-m6/pptx-real-results
ctest --test-dir build/pptx-m6 -R native-pptx-real --output-on-failure
```

Linux/macOS 使用相应的 `libexreader.so` / `libexreader.dylib`。运行依赖与生成器相同。
默认检查 12 份有效件全部 31 页及 3 份坏件；`--file twenty` 可单独复测性能，
`--repeats` 默认每页 5 次。输出目录保留每页实际位图、去文字位图和 `matrix.json`，
JSON 包含全部采样点、RGB、bbox、字形差分像素数、库 SHA-256 与每次耗时。

coverage 严格检查非白像素 bbox 覆盖完整形状框并集，容差 4px；文字框不剔除。
颜色点仅由参考结构决定，每页 12 个不同点，轮流取各填充区域和页面的稳定内部点，
避开参考侧估算的文字区域与颜色边界；每通道容差 4，至少 10/12 才通过。
纯文本页的这 12 点只检查背景，文字由独立存在性检查负责，不验证文字 RGB。

文字存在性通过原包与清空 `txBody` 段落内容后的同包渲染差分测量，保留形状几何、
图片和填充，仅在参考文本框范围累计差异像素。因此深色填充或照片不能冒充字形。
去文字包也重新检查警告，防止较长的字体警告截断后遮住其他结构警告。
所有非字体警告、未实现的参考结构、采样不足、颜色失败均计失败，矩阵返回非零。

新增 CTest 为 `native-pptx-real-matrix`、`native-pptx-real-reproducible` 和
`native-pptx-real-oracle`。后者以全白、错位、错色、丢文字进行故障注入，
验证矩阵会拒绝这些错误；前者继续保留真实语料暴露的失败。

`twenty` 的结构定位：第 6 页为简单平铺图片；第 10 页为圆角形状的图片填充；
第 14 页有水平翻转；第 18 页有 90° 旋转及垂直翻转；第 1、5、9、13、17 页
有圆、三角形和 3pt 直线。表格使用显式自定义样式，没有未实现的 Office 预设表格样式。

## 实测边界

当前语料与矩阵不宣称全部通过。纯文本的形状框包含排版余量，不能直接等同于非白
字形像素框。标题页的 `python-pptx` 形状框是 `(96,190,864,290)`，当前宿主实测
字形像素框为 `(96,200,440,241)`；按“非白 bbox 覆盖形状并集、误差 ±4px”的
字面判据会失败。项目符号页也有相同差异。原始文本框保留正常的排版尺寸，矩阵
继续报告失败。

引擎当前读取形状上的 `a:gradFill`，没有绘制幻灯片 `p:bg/p:bgPr/a:gradFill`。
因此 `gradient-alpha` 的真正背景渐变缺失，当前实测 `(8,8)` 为白色；依赖背景的
半透明叠加颜色也会发生差异。语料保留该结构以使边界可重复验证。字体回退或缺字
警告按验收规则允许；其他警告仍由矩阵判失败。
