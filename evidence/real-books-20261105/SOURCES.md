# 补充语料来源与结构核验 · 2026-11-05

本目录只含元数据与结果；原始书籍、构造 PDF、下载 EPUB、PNG 数据、字体、封面和正文均保存在仓库外。原始真书清单 RESULTS.csv 仍为去重后的 15 本；两项补充单列 SUPPLEMENTAL-RESULTS.csv，未记账。

补充 CSV 在原九列后增加 render、image_only、vertical_rl_recognized。草枕的 API 渲染成功与竖排识别失败分别记录，不将渲染退出码 0 当作竖排能力通过；n/a 表示该项不适用。first_error 只记录引擎错误，未将外部能力判定伪装成引擎报错。

本轮未在交互桌面上创建任何可见窗口。CLI 均使用 Start-Process -WindowStyle Hidden -Wait，父进程为 CREATE_NO_WINDOW + SW_HIDE，输出重定向至仓库外临时文件后仅保留统计。

## 1. 构造型扫描件

验收登记：2026-11-05 owner 明确确认“扫描件通过，记账”。登记范围为本构造件的 20 页解析/渲染与 image-only 结构；不授予真实扫描噪点或 OCR 能力结论。

- 文件：`malcolm-x-first-20-pages-image-only-200dpi.pdf`；8859207 bytes；SHA-256 `b3fd154b431e9338b3a562d2fa1259723cd51bfc7ca9497ce067cbd4dd979b37`。
- 来源：本地 FinalBooks 中 `The Autobiography of Malcolm X. (Malcolm X, Alex Haley) (z-library.sk, 1lib.sk, z-lib.sk).pdf`；源 SHA-256 `c9373b7dbda128fea031616b444ca490a3cd59dccb3f02cb2512fd9957a0fdb7`。来源无下载 URL。
- 许可：本地商业书，未取得/未核实开放许可；构造处理不赋予新开放许可，不上传或分发。
- 是否构造：是。标注：**构造型扫描件，结构等价，非扫描噪点样本**。取原 PDF 前 20 页，以 PyMuPDF 200 dpi、RGB、不透明渲染成 PNG 字节流，再逐页插入全新 PDF。PNG 仅在内存中；没有复制源 PDF 页对象、文字、字体、批注或目录。
- 工具：本地已有 PyMuPDF 1.28.2；未向仓库添加任何依赖。
- 独立结构验证：20 页；图像资源 20；字体资源 0；提取文本字符 0；文字绘制运算符 0。原 PDF 对应 20 页提取文本字符为 74778（只记录数量）。
- 引擎结果：open=ok；render=True；parts=1；pages=20；first_render_ms=508.082；exit=0。
- image-only 判据：CLI 原生 JSON 的 text_bytes=0，加上上述逐页图像/字体/文本结构验证。CLI 没有名为 image_only 的字段，不把推断伪装成 CLI 字段；这项测试不测 OCR。

实际 CLI JSON：
```json
{"schema":1,"engine_version":"3.42.0","status":0,"stage":"text","parts":1,"completed_parts":1,"pages":20,"text_bytes":0,"complete":true}
```

## 2. 公开日文竖排样本《草枕》

以下是修复前 SDK 的原始观测。2026-11-05 已按 owner 授权修复 CSS 属性前缀别名；新候选的 462 页全部进入 vertical-rl、107609 个竖排字形，详见 [修复与自洽性证据](CSS-ALIASES.md)。保留原始结果，不覆盖旧二进制的失败证据。

- 文件：`kusamakura-japanese-vertical-writing.epub`；17940673 bytes；SHA-256 `6d4d4ed5eda3f612e3263c54fa0f74ccfa87260f43e81bb58ea658636e52eeb7`。
- 来源：IDPF/W3C EPUB 3 Samples；作者夏目漱石；版本为 20230704 release 的原包，未修改样式或内容。
- 原包下载 URL：[kusamakura-japanese-vertical-writing.epub](https://github.com/IDPF/epub3-samples/releases/download/20230704/kusamakura-japanese-vertical-writing.epub)；HTTP 200。
- 项目来源页：[EPUB 3 Samples](https://idpf.github.io/epub3-samples/30/samples.html)。
- 精确许可依据：下载包 OPS/package.opf 内 dcterms:license（[对应源码](https://github.com/IDPF/epub3-samples/blob/20230704/30/kusamakura-japanese-vertical-writing/OPS/package.opf)）。无 refines 的许可为 [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)；refines 指向两个音频的许可为 [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/)。本轮不播放音频。不能用项目默认 CC BY-SA 3.0 覆盖包内的逐项声明。
- 是否构造：否；下载成功，因此未启用青空文库第二来源或合成夹具兜底。包内 dcterms:source 指向 [青空文库原作条目](https://www.aozora.gr.jp/cards/000148/card776.html)。
- 样式事实：OPS/css/vertical.css 的有效声明是 -epub-writing-mode: vertical-rl；另有注释掉的 horizontal-tb 字样，不能把注释当成有效 CSS。未将前缀改成标准 writing-mode。
- 引擎结果：open=ok；render=True；parts=16；pages=314；first_render_ms=9.662；exit=0。
- vertical-rl 判定：**未识别该原样样本的竖排：布局模式/字形标志均未进入 vertical-rl；记录为兼容性缺口**。实际逐页统计：horizontal_pages=314，vertical_rl_pages=0，vertical_lr_pages=0；vertical_glyphs=0；missing_glyphs=0。
- 探针只读取 exr_layout_writing_mode() 与 EXR_GLYPH_VERTICAL / EXR_GLYPH_MISSING 计数，位图仍由原 CLI 的渲染调用生成。没有用阅读方向 rtl 或 CSS 文本的存在冒充引擎已识别。

实际 CLI JSON：
```json
{"schema":1,"engine_version":"3.42.0","status":0,"stage":"paginate","parts":16,"completed_parts":16,"pages":314,"text_bytes":322088,"complete":true}
```

实际布局统计：
```json
{"horizontal_pages":314,"vertical_rl_pages":0,"vertical_lr_pages":0,"glyphs":107609,"vertical_glyphs":0,"missing_glyphs":0}
```

## 边界与复核

- SDK DLL SHA-256：`3cde779eb65b0ace00165b9dbe18d85a44833653d374567301a8a0bf1e0c4ab8`，与先前 15 本实测相同；两个 CLI 均在仓库外 include 原 tools/check_document.c，仅添加计时与只读统计。
- 竖排样本使用已交付 Reader.otf（CJK 字体），SHA-256 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`；扫描 PDF 使用原 Arial。字体不入库。
- 不改产品代码、不修 bug、不跑 CI、不改 catalog 或计账状态。图像只有构造扫描用途；本次不交付书籍或渲染图片。

## 标准竖排语法对照（既有测试夹具，不计入语料）

- 对照为仓库既有 tests/fixtures/float-vertical-rl.epub，MIT 测试夹具；含标准 writing-mode:vertical-rl，未修改文件。
- 原 CLI 与只读统计包装的完整 JSON 和退出码一致；标准竖排对照实际统计如下。

```json
{"horizontal_pages":1,"vertical_rl_pages":1,"vertical_lr_pages":0,"glyphs":214,"vertical_glyphs":199,"missing_glyphs":0}
```

标准语法已进入 vertical-rl 且产生竖排字形。因此已确认的缺口是《草枕》原包的竖排样式兼容/应用路径；不能归结为“引擎完全不支持竖排”。原包使用 -epub-writing-mode 前缀，具体兼容原因本轮只记录、不修复。
