# PPT M6 真实二进制语料

本目录有 **8 份有效 `.ppt`（共 27 页）和 2 份坏文件**。所有有效文件均由
Windows 上的 Microsoft PowerPoint COM 现场创建，以 `SaveAs(path, 1)` 保存为
`ppSaveAsPresentation`，随后重新打开读取页数、页面尺寸和叶形状边界。
二进制结果、逐件 manifest 和总 [manifest.json](manifest.json) 均入库，CI 不需要 Office。

| 文件 | 页数 | 特性 |
|---|---:|---|
| [title/title.ppt](title/title.ppt) | 1 | 纯标题页、无填充文本框、16:9 |
| [bullets/bullets.ppt](bullets/bullets.ppt) | 1 | 项目符号列表、三级缩进 |
| [image-text/image-text.ppt](image-text/image-text.ppt) | 1 | 原创 PNG 与文字混排 |
| [merged-table/merged-table.ppt](merged-table/merged-table.ppt) | 1 | 真正的 3×3 表格、横向与纵向合并、单元格边框 |
| [chinese/chinese.ppt](chinese/chinese.ppt) | 1 | 中文标题、正文、表格 |
| [standard-4x3/standard-4x3.ppt](standard-4x3/standard-4x3.ppt) | 1 | 4:3、矩形、椭圆、直线、仅边框矩形 |
| [wide-16x9/wide-16x9.ppt](wide-16x9/wide-16x9.ppt) | 20 | 16:9、20 页性能语料 |
| [nested-groups/nested-groups.ppt](nested-groups/nested-groups.ppt) | 1 | 两层真实组、内层组缩放、矩形/椭圆/三角形 |
| [bad-truncated/bad-truncated.ppt](bad-truncated/bad-truncated.ppt) | 0 | 原标题件截断一半，期望 `5 / EXR_FORMAT` |
| [bad-header/bad-header.ppt](bad-header/bad-header.ppt) | 0 | 原标题件 CFB 头部八字节损坏，期望 `5 / EXR_FORMAT` |

生成源 [generate.py](generate.py) 和原创图像按 [MIT LICENSE](LICENSE) 发布。
`image-text/source.png` 由标准库 `struct`/`zlib` 写入 filter-0、level-0 PNG；没有 ZIP 容器。
每件 `powerpoint.png` 是保存后重新打开的 PowerPoint 第 1 页导出预览，IDAT 经标准库
重新编码为 level-0，不参与指标阈值选择。

## 生成与完整性检查

手动生成需要 Windows 和安装的 PowerPoint，Python 仅使用标准库，通过系统
`powershell.exe` 调用 COM。重新生成会产生新的 Office 元数据及新的 SHA-256：

```powershell
python -S tests/fixtures/ppt-real/generate.py
```

CI 的检查命令跨平台，只检查现有文件是否存在、大小和 SHA-256 是否与逐件 manifest
一致，并检查总 manifest 是否等于逐件汇总。它不会导入 COM、调用 PowerPoint、联网或重新生成：

```powershell
python -S tests/fixtures/ppt-real/generate.py --check
```

manifest 包含 `powerpoint_version` 和重新打开后实际读取的 `powerpoint_reported_slides`。
辅助预览和原创 PNG 也记录大小与哈希。`oracle` 来自生成意图（几何类型、填充、文本属性）
和保存后 COM 读取的实际边界；组展开为叶形状，合并单元格只保留覆盖范围内的主单元格。
每页的 12 个不同颜色采样点在生成源中定义，避开文字和边界，颜色不从引擎位图读取。

## 逐页验收

```powershell
python -S tests/ppt_real_matrix.py --library build/ppt-m6/libexreader.dll --output build/ppt-m6/ppt-real-results
ctest --test-dir build/ppt-m6 -R native-ppt-real --output-on-failure
```

Linux/macOS 使用对应共享库。`native-ppt-real-matrix`、`native-ppt-real-reproducible`、
`native-ppt-real-oracle` 均使用 `python -S`。

coverage 分别检查有填充形状、只有文本的形状和纯边框/线条；文字用原始文件与关闭
TextCharsAtom/TextBytesAtom 后的二次渲染差分判断。变体只改记录类型，保留长度和偏移；
照片与深色填充不能充当字形。
每页输出 `file#slide coverage=ok color=12/12 text=ok`，颜色至少 10/12 点通过。
只容忍宿主字体回退或缺字警告，其他警告均失败。

`title.ppt` 与 `wide-16x9.ppt` 的每页具有完全相同的标题、尺寸和形状。
性能在同一台机器测量单页基线 T1 与 20 页 T20 的 per-slide 中位数，要求
`T20 <= T1 * 3.0`；最大单次耗时一并输出供验收记录，不用绝对毫秒阈值跨机器判定。
