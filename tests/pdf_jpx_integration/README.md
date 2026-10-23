# JPX 的真实 PDF 闭环

仅在 GitHub Actions 安装 SDK 后运行。构建复用 `tests/reading_real`，其 `reading-real-benchmark` 只链接已安装的公开 SDK。云端需要 Pillow JPEG2000 支持与 `pdftoppm`：

```sh
python3 tests/pdf_jpx_integration/check.py --binary build/reading-real-consumer/reading-real-benchmark --font build/reading-real-font/Reader.otf --output build/pdf-jpx-on
```

关闭 JPX 并重新安装/构建消费者后，对同一生成计划运行 `--expect-off --output build/pdf-jpx-off`。到达 decoder 的 PDF 均须明确返回 `EXR_UNSUPPORTED`；非末端 filter、非 null 参数、inline、stencil 在解码前仍以 `EXR_FORMAT` 拒绝。所有拒绝均没有 PPM。

夹具由 Pillow lossless JP2/裸 J2K 和最小 PDF 对象图生成，期待值来自固定源像素；`plan.json` 在第一次 SDK 执行之前落盘。十项正例用 2×2 像素逐点对比源值及独立 Poppler：Gray8/16、RGB8、ASCII85→JPX、Indexed8 原索引和 `/Decode [0 255]`、独立 soft mask 与 color-key mask。Gray 的反转 Decode 按 JPX 忽略规则验证；Indexed 非默认 Decode 待规范结论，不加入本计划。

十二项负例覆盖损坏/截断、维度/组件不匹配、signed/32bit 精度、子采样、嵌入 alpha、JPX 非末端、非 null 参数、inline、stencil；拒绝均要求无 PPM。精度等不支持的元数据允许 FORMAT 或 UNSUPPORTED，两者必须显式失败。该小型合成套件验证真实公开 SDK 集成，不代替 NASA 或其他真实 PDF 验收。
