# JPX 的真实 PDF 闭环

仅在 GitHub Actions 安装 SDK 后运行。构建复用 `tests/reading_real`，其 `reading-real-benchmark` 只链接已安装的公开 SDK。云端需要 Pillow JPEG2000 支持与 `pdftoppm`：

```sh
python3 tests/pdf_jpx_integration/check.py --binary build/reading-real-consumer/reading-real-benchmark --font build/reading-real-font/Reader.otf --output build/pdf-jpx-on
```

关闭 JPX 并重新安装/构建消费者后，对同一生成计划运行 `--expect-off --output build/pdf-jpx-off`。到达 decoder 的 PDF 均须明确返回 `EXR_UNSUPPORTED`；非末端 filter、非 null 参数、inline、stencil 在解码前仍以 `EXR_FORMAT` 拒绝。所有拒绝均没有 PPM。

夹具由 Pillow lossless JP2/裸 J2K 和最小 PDF 对象图生成，期待值来自固定源像素；`plan.json` 在第一次 SDK 执行之前落盘。十一项正例的 native 2×2 四像素始终精确对比源值：Gray8/16、RGB8、ASCII85→JPX、Indexed8 原索引和 `/Decode [0 255]`、独立 soft mask 与 color-key mask。Gray 和 Indexed 的反转 Decode 均按 JPX 非 mask 忽略规则验证，Indexed 仍按原始索引取 palette。

独立 Poppler 以 720dpi 生成 20×20 图，四个色块中心及各自 3×3 内部区域必须逐点精确等于相同源值。72dpi 的 2×2 Poppler 输出发生边界重采样，原失败保留；云端诊断 run `39898120117` / job `120233168533` 核原工件 ZIP SHA 后，在同一原 PDF 的 720dpi 网格确认四块源值。此调整只改变独立参考的采样位置，native 原 2×2 精确断言不变。

Decode 语义按官方 PDF §3.3.8（印刷第 89 页）与 Table 4.39（第 341 页）；云端原文核对记录为 run `39896660928` / job `120228578772`。

十三项负例覆盖损坏/截断、维度/组件不匹配、signed/32bit 精度、子采样、RGBA 组件不匹配、显式 CDEF alpha、JPX 非末端、非 null 参数、inline、stencil；拒绝均要求无 PPM。原名 `embedded-alpha` 的 Pillow 样本由同次原 ZIP 诊断证明为四组件、没有 CDEF；其 PDF 声明 RGB 三组件，应精确以 FORMAT 拒绝，现明确命名 `rgba-components-mismatch`。另加合法 RGBA CDEF 定义（Pillow 独立重开确认）专测 alpha metadata 的 UNSUPPORTED 边界。32bit 变异可能由 codestream 头解析器以 FORMAT 拒绝，也可能到达 adapter 并以 UNSUPPORTED 拒绝；其余用例固定单一状态。该小型合成套件验证真实公开 SDK 集成，不代替 NASA 或其他真实 PDF 验收。
