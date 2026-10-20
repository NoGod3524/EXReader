# 整本文档兼容验证

`tools/check_document.c` 对 EPUB 逐部分加载、分页并绘制每一页；其他重排格式使用完整文档。
PDF/CBZ逐页绘制并请求文字层。固定页最长边不超过720像素，重排页为720×1040。
检查只证明该配置下打开、遍历、绘制和提取的结果；像素保真、字体覆盖、保存及规范一致性另行验收。

```sh
stage/bin/exreader-check-document book.epub font.otf 0
python tools/check_corpus.py stage/bin/exreader-check-document font.otf corpus/manifest.json evidence --timeout 120
```

最后一个原生参数是页数上限，0表示整本。到达上限且仍有页面时输出`complete:false`并非零退出。
恰好在最后一页结束仍可完整通过。处理错误会保留失败阶段、状态码和已完成的部分/页数。
`tests/check_document_probe.py`覆盖整本/精确页数/截断、错误输入及汇总拒绝路径；CI以`native-document-probe`运行。

语料清单可以是数组，或包含`files`、`complete`、`target`的对象。每项至少包含相对`path`和`sha256`。
验收须预先声明`expected`中的`status`与`complete`；预期拒绝还须提供`expectation_reason`。
未声明预期的文件保留为`untriaged`。观察结果不能自动写回为预期。

Python驱动每份文件启动独立进程，`--workers`可设置1–8个并行文档进程，默认1个。
`--timeout`限制各进程墙钟时间，不作为可靠性CPU预算。保留stdout、stderr、退出码、时间和报告散列；
记录字体、程序、同目录运行库、语料清单及工具源码散列。输入路径必须在语料根目录内。
重复路径、缺文件/散列不符、无效报告、异常退出、超时、输入或运行环境变化、
结果与预期不符均不能通过。使用`--max-files`或`--max-pages`只能得到受限覆盖；
尚未收齐的清单、目标数量不符或未分类文件也拒绝整批验收。证据目录不得覆盖。

`tools/fetch_gutenberg_corpus.ps1`在Windows通过系统HTTPS信任链获取真实EPUB3及其RDF元数据：

```powershell
pwsh -NoProfile -File tools/fetch_gutenberg_corpus.ps1 -Output C:/corpus/gutenberg -Count 500
```

按目录ID升序选择，筛选RDF声明为美国公版且提供带图EPUB3的条目，保留原书中的Gutenberg条款。
本工具不依据引擎结果挑选书籍。每次请求至少间隔500ms，收集失败和未选择原因均记录；
清单按条目保存进度，续跑先核对已有书籍和元数据散列。原始下载错误保存在收集目录。
现有`tests/corpus/manifest.json`及历史外部PDF保持独立，不由新收集工具覆盖。

当前结果、原始报告路径及明确未通过的项目见 `docs/validation/2026-10-20-corpus-performance.json`。
完整数量与规范/保真目标沿用 `docs/HANDOFF.md`，合成语料和真实书籍分别统计。
