# PPT-M6 真实语料逐页验收

8 份有效 `.ppt` 全部 `status=0 / code=0`，引擎页数均与 PowerPoint 16.0 重新打开文件后报告的页数一致。共 27 页，逐页 coverage、color、text 全部通过；另外 2 份坏文件从文件路径和内存打开均返回 `5 / EXR_FORMAT`。矩阵最终结果为 `MATRIX files=10 passed=10 failed=0`。

本次从 `main 1ac25109` 开始，在 Windows / Python 3.14.7 上完成 Release 构建。矩阵使用的共享库 SHA-256 为 `7a904c8ee8e3ed0acd36b0b568bfb22a4f9dcae30b63813eae3b4c767c9f0aee`；逐形状边界、12 点实际 RGB、字形差分像素和每次渲染耗时保存在 [matrix.json](matrix.json)，控制台原始输出见 [matrix-raw.txt](matrix-raw.txt)。

**语料与来源。** 下列 8 份有效件、2 份坏件均已入库，逐件有独立 `manifest.json`，另有[总 manifest](../../tests/fixtures/ppt-real/manifest.json)。有效件由 Python 标准库驱动 PowerShell COM，使用 `SaveAs(path, 1)` 生成二进制格式；保存后再次通过 COM 读取页数、尺寸和叶形状边界。[生成实录](generate-com.txt)记录 PowerPoint 16.0 实际报告。`wide-16x9` 的 20 页与单页 `title` 具有相同尺寸、标题内容、几何和采样点，用于同机相对性能比较。

| 文件 | COM / 引擎页数 | 特性 | 大小（字节） | SHA-256 前 8 位 |
|---|---:|---|---:|---|
| [title.ppt](../../tests/fixtures/ppt-real/title/title.ppt) | 1 / 1 | 纯标题、无填充文本框、16:9 | 302592 | `02810801` |
| [bullets.ppt](../../tests/fixtures/ppt-real/bullets/bullets.ppt) | 1 / 1 | 项目符号、三级缩进 | 303104 | `15d81e42` |
| [image-text.ppt](../../tests/fixtures/ppt-real/image-text/image-text.ppt) | 1 / 1 | 原创 PNG、图片与文字混排 | 415744 | `7ca56a25` |
| [merged-table.ppt](../../tests/fixtures/ppt-real/merged-table/merged-table.ppt) | 1 / 1 | 3×3 真表格、横纵合并、单元格边框 | 322560 | `7aa46eae` |
| [chinese.ppt](../../tests/fixtures/ppt-real/chinese/chinese.ppt) | 1 / 1 | 中文标题、正文、表格 | 325632 | `e3af1ac6` |
| [standard-4x3.ppt](../../tests/fixtures/ppt-real/standard-4x3/standard-4x3.ppt) | 1 / 1 | 4:3、矩形、椭圆、直线、纯边框矩形 | 306688 | `9c01d4ae` |
| [wide-16x9.ppt](../../tests/fixtures/ppt-real/wide-16x9/wide-16x9.ppt) | 20 / 20 | 16:9、20 页性能语料 | 313856 | `253fc60d` |
| [nested-groups.ppt](../../tests/fixtures/ppt-real/nested-groups/nested-groups.ppt) | 1 / 1 | 两层真实组、内层缩放 1.08、矩形/椭圆/三角形 | 310272 | `2b620119` |

表格通过 COM `Cell.Merge` 完成横向与纵向合并；组通过真实 `Group()` 和 `ScaleWidth/ScaleHeight` 生成。颜色采样点来自作者定义，几何边界来自保存后 COM，均未读取引擎像素来选择。各有效件的 PowerPoint 首帧导出预览也独立核对为 12/12 个采样点匹配。原创 PNG 和 PowerPoint 预览的 IDAT 均使用标准库重压为 level-0，文件和辅助资产的大小、SHA-256 均记入 manifest。

**逐页全量输出。** coverage 按有填充、只有文本、纯边框/线条分别判定；本次分别检查 22、33、2 个区域。每页检查 12 个不同颜色点，每通道容差 4，至少 10/12 才通过；本次全部 12/12。文字通过原件与等长禁用 TextCharsAtom/TextBytesAtom 后的二次渲染差分检查，逐文本框要求字形存在。只有宿主字体回退或缺字警告可放行；本次仅 `bullets` 出现 `font fallback=Aptos Display`，其余有效件打开警告为空。

```text
bullets.ppt#1 coverage=ok color=12/12 text=ok
chinese.ppt#1 coverage=ok color=12/12 text=ok
image-text.ppt#1 coverage=ok color=12/12 text=ok
merged-table.ppt#1 coverage=ok color=12/12 text=ok
nested-groups.ppt#1 coverage=ok color=12/12 text=ok
standard-4x3.ppt#1 coverage=ok color=12/12 text=ok
title.ppt#1 coverage=ok color=12/12 text=ok
wide-16x9.ppt#1 coverage=ok color=12/12 text=ok
wide-16x9.ppt#2 coverage=ok color=12/12 text=ok
wide-16x9.ppt#3 coverage=ok color=12/12 text=ok
wide-16x9.ppt#4 coverage=ok color=12/12 text=ok
wide-16x9.ppt#5 coverage=ok color=12/12 text=ok
wide-16x9.ppt#6 coverage=ok color=12/12 text=ok
wide-16x9.ppt#7 coverage=ok color=12/12 text=ok
wide-16x9.ppt#8 coverage=ok color=12/12 text=ok
wide-16x9.ppt#9 coverage=ok color=12/12 text=ok
wide-16x9.ppt#10 coverage=ok color=12/12 text=ok
wide-16x9.ppt#11 coverage=ok color=12/12 text=ok
wide-16x9.ppt#12 coverage=ok color=12/12 text=ok
wide-16x9.ppt#13 coverage=ok color=12/12 text=ok
wide-16x9.ppt#14 coverage=ok color=12/12 text=ok
wide-16x9.ppt#15 coverage=ok color=12/12 text=ok
wide-16x9.ppt#16 coverage=ok color=12/12 text=ok
wide-16x9.ppt#17 coverage=ok color=12/12 text=ok
wide-16x9.ppt#18 coverage=ok color=12/12 text=ok
wide-16x9.ppt#19 coverage=ok color=12/12 text=ok
wide-16x9.ppt#20 coverage=ok color=12/12 text=ok
```

**性能。** 每页渲染 5 次取中位数，T1 取单页文档的 per-slide 中位数，T20 取 20 页文档各页中位数的中位数。`1.4184 <= 1.3231 × 3.0 = 3.9693 ms`，相对门槛通过。此基准中的最大单次渲染为 1.9648 ms；全语料全部测量的最大值为 8.5500 ms（`image-text#1`），两者均小于 200 ms。绝对耗时只作本机实测记录，CTest 仅按同机比值判定。

```text
PERFORMANCE T1=1.323ms T20=1.418ms ratio=1.072 limit=3.000 result=ok max=1.965ms max<200ms=yes (observed; relative gate only)
```

**坏文件实测。** `status/code` 在文件路径和内存两种打开方式中都要求同时为 5，并要求没有文档句柄；两个文件均正常返回，进程未崩溃。

| 文件 | 大小（字节） | SHA-256 前 8 位 | 文件 status/code | 内存 status/code | 实际消息 |
|---|---:|---|---|---|---|
| `bad-header.ppt` | 302592 | `1e461b38` | 5 / 5 | 5 / 5 | `CFB invalid signature at offset 0` |
| `bad-truncated.ppt` | 151296 | `447d35b2` | 5 / 5 | 5 / 5 | `CFB truncated sector at offset 151296` |

**复现与回归。** 以下验证均已实际运行，完整输出保留在对应文件。

- [`generate.py --check`](generate-check.txt)：exit 0，`10 files, 27 valid slides; check=ok`。仅核对已入库文件存在、大小、SHA-256 与 manifest 汇总，不启动 Office、不重新生成。
- [`python -S tests/test_ppt_real_oracle.py`](oracle.txt)：exit 0。全白、错位、错色、丢文字、文字溢出、遗漏文本框、丢边框、非白背景冒充形状等故障注入均被拒绝；CFB mini/regular stream 和 512/4096 字节扇区的等长文本修改均通过。
- [标准库与静态检查](static-checks.txt)：`no_site=1`、`site-packages imports=0`、`stdlib import exit=0`；三个新 Python 文件搜索 `lxml / PIL` 输出为空。新脚本及复用的 PPTX 矩阵、ABI 包装和 CFB 测试模块均仅导入标准库或仓库模块。`git diff --check` exit 0；`tests/check_reading_release.py` 未修改。
- [PPT M1–M5 回归](ctest-m1-m5.txt)：`100% tests passed out of 51`。其中 M1 为 6 组，M2–M5 共 45 组（形状 12、填充 8、文本 15、表格 10），全部通过。
- [新增 3 项 CTest](ctest-real.txt)：`native-ppt-real-matrix`、`native-ppt-real-reproducible`、`native-ppt-real-oracle` 实际 `3/3` 通过，耗时 7.82 秒，exit 0，全部通过 `python -S` 运行。
- [全量 CTest](ctest-all.txt)：重新配置 CMake 后，包含新增 3 项在内的 `563/563` 全部通过，耗时 109.91 秒，exit 0；排除 `sdk-release / sdk-doc-coverage`，环境为 `PYTHONUTF8=1`。之前的[既有测试独立运行](ctest-existing-560.txt)也为 `560/560` 通过。Windows 首轮的 DOCX E5 测试受默认 cp1252 解码影响；设置上述环境变量后通过，未修改该测试源码，首轮记录保留在 [ctest-all-initial.txt](ctest-all-initial.txt)。
- [外部 harness 的 `ops/prepush-check.ps1`](prepush.txt)：对本工作树运行并返回 exit 0，冲突标记、code/docs 结构和 SDK 文档检查全部通过，输出 `全部通过 —— 可以推`；实际路径和 `-Worktree $PWD` 参数见下方复测命令。

可从仓库根目录复测：

```powershell
python -S tests/fixtures/ppt-real/generate.py --check
python -S tests/test_ppt_real_oracle.py
python -S tests/ppt_real_matrix.py --library ../exr-build-pptm6/libexreader.dll --output ../exr-build-pptm6/ppt-real-results
ctest --test-dir ../exr-build-pptm6 -R native-ppt-real --output-on-failure
$env:PYTHONUTF8 = '1'
ctest --test-dir ../exr-build-pptm6 -E 'sdk-release|sdk-doc-coverage' --output-on-failure
powershell -NoProfile -ExecutionPolicy Bypass -File C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1 -Worktree $PWD
```

**已知边界。** 本次真实语料已覆盖矩形、椭圆、三角形、直线、纯边框矩形和组缩放。以下限制仍存在，未以跳过页的方式隐藏：

- 非零 `rotation` 的形状或组会产生 `unsupported`，整个形状或组不绘制；当前不是任意角度旋转实现。
- 圆角矩形及其余 OfficeArt 预设几何尚未实现；无对应路径的形状可能省略几何并产生 `unsupported`。本次补齐的是类型 5 三角形。
- 渐变仍简化为两个端点之间的水平线性插值；任意角度、径向类型和中间色标不能按 PowerPoint 原样呈现，并报告 `gradient-horizontal` 或 `gradient-missing`。
- 填充透明度未应用，颜色按不透明值输出；图片裁切属性未应用，图片按整个原始位图拉伸到目标框。
- 母版目前读取配色与文本样式，母版装饰形状和图片不会作为页面前景绘制。
- 字体形状和排版尚非像素级等同。实际 `nested-groups` 的标题及 `Planning` 字宽比 [PowerPoint 预览](../../tests/fixtures/ppt-real/nested-groups/powerpoint.png)窄。当前 text 指标验证每个文本框字形存在及框内覆盖范围，不比较字体轮廓、字距或换行位置。
