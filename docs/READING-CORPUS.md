# 阅读核心语料（R2）

R2 用可复现文档解决 EPUB 超时、PDF 打开与绘制故障。优先让日常阅读可靠、快速、内存有界；参考引擎用于分类和定位。

## 首批合成 smoke

冻结清单为 [`tools/reading_core/smoke-manifest.json`](../tools/reading_core/smoke-manifest.json)，
输入根为 `tests/fixtures`。九份文件分别覆盖 TXT、HTML、FB2、EPUB、DOCX、RTF、MOBI、CBZ、PDF，
逐项登记字节数、SHA-256、合成身份及运行前期望 `status=0, complete=true`。
`complete:true` 表示这份九项清单已收齐；运行结果由云端另行产生。

选择依据为已有原生测试契约：`tests/test_core.c:test_formats` 的七种重排正例、
`tests/test_cbz.c`，以及 `tests/check_document_probe.py` 的整本 TXT/CBZ/PDF 检查。
重排正例的打开/文字契约不等于本次完整绘制已经通过；首次 smoke 将独立检查整本遍历。
PDF 采用 `pdf-color/shading-axial.pdf`。`pdf-public-text.pdf` 的部分页面按
`tests/test_fixed_pdf.c:semantic_text` 应返回格式错误，不能把它作为全书成功正例。

复用现有检查器，在 GitHub runner 执行：

```sh
python3 tools/check_corpus.py build/reading-core/exreader-check-document \
  tests/fixtures/fonts/primary.ttf tools/reading_core/smoke-manifest.json \
  build/reading-core/smoke --root tests/fixtures --timeout 120
```

二进制路径以实际构建目录为准。`input_root` 是清单说明字段，必须显式传入 `--root`。
每次运行使用新输出目录，逐文件保留报告、日志、状态与散列；使用完整清单、完整页数。
现有检查器验证输入 SHA-256，`bytes` 是登记元数据。
失败须修复或作为开放缺陷保留，不能依据观察结果将成功期望改成拒绝。

本批仅覆盖打开、完整分页/绘制与文字提取，不授予像素保真、保存、字体覆盖或性能结论。
九份均为仓库原创合成测试资源，对真实语料完成数的贡献为 **0**；历史 `0/1710` 登记保持原样。

## 下一批真实文档

先登记能代表实际阅读问题的小批 EPUB/PDF，不以重新收集 1710 份为 R2 的启动条件。
从具有明确文件身份与使用许可的来源选择：优先可重获的历史失败原件、用户授权的故障文档，
再补充 Project Gutenberg 等公开来源的 EPUB，以及作者明确许可的 PDF 技术文档。
每份记录原始 URL/来源、作者、许可依据、SHA-256、字节数与目标阅读能力，运行前提交清单。
没有公开分发权限的用户文档只进入获授权的私有云端输入；不能上传到公开仓库或公开工件。

复用 [`CORPUS_VALIDATION.md`](CORPUS_VALIDATION.md) 的逐进程检查和失败分类。
历史大批量协议及其权限记录见 [`COMPAT-CORPUS-PARALLEL.md`](COMPAT-CORPUS-PARALLEL.md)，
已有清单与数量不修改。R2 的小批缺陷集独立登记，不能假装满足旧协议的整批验收。
执行身份绑定源码、字体、工具及输入；首次登记后保留失败，并以新源码追加重跑证据。

## 继承历史问题

历史 EPUB 500 份为 483 完成、11 超时、5 资源限制、1 参数状态，原批未验收。
先恢复 11 份超时输入的原散列和原报告，在固定云端配置测定打开、装载、分页和绘制阶段，
再按热点修复。5 份资源限制和参数状态分别保留，不能合并成超时或自动视为正确拒绝。

历史 PDF 122 份中 49 完成，另有 54 份参考完成而本引擎拒绝、8 份参考修复、
4 份待审查、7 份不支持。按这些原分类恢复输入和证据，优先修复受支持范围的打开/绘制故障。
参考程序完成只帮助诊断；不能直接据此判定标准符合性或像素正确性。

原件身份与许可未恢复时登记为“待恢复输入”，不以同名文件、替代文档或新合成例替换原失败。
历史证据保留在 `docs/validation/2026-10-20-corpus-performance.json` 与
`docs/validation/2026-10-20-wp6-compatibility.json`。修复后用同一输入、原成功期望重跑，
并把可公开的最小回归例加入常规检查。峰值内存和性能预算由 R3/R4 测量确定。
