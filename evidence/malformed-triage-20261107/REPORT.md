# EPUB 容错待查定性与严格校验（2026-11-07）

本次以 main `c9dfc6c1` 为改前版本。默认打开入口保持宽容；校验工具可显式调用 `exr_epub_validate(path, error)`、`exr_epub_validate_memory(data, size, error)`，或使用 `exreader-check-document input.epub font.ttf --strict`。严格校验成功后再走正常打开、分页与渲染。

## 八类定性

结论针对原报告的具体变体，严格模式是结构校验标准。原报告的“通过”指**有错误文本的明确拒绝**，不表示这些损坏文件能够阅读。

| 类别 | 变体数 | 结论 | 理由与宽容边界 |
|---|---:|---|---|
| 尾部截断 | 128 | 应当报错 | 每条都删除原 ZIP 尾部，EOCD/中央目录不再完整；本批没有足以证明完整包的恢复结果。 |
| 中段缺失 | 128 | 应当报错 | 删除实际成员区字节而不重写目录偏移，后续本地头位置或内容校验失配，不能保证所读内容完整。 |
| 目录声明不符 | 128 | 应当报错 | 每条只改一个目录字段，声明与保留的实际结构冲突；严格模式必须核对，默认允许其中仅影响未读取 mimetype 的 56 条。 |
| 缺 container.xml | 128 | 应当报错 | 缺少 META-INF/container.xml，无法从指定根包入口确定阅读顺序；本批默认已经明确拒绝。 |
| mimetype 不符 | 128 | 应当报错 | 严格模式必须核对 OCF 标识；默认阅读可以根据有效 container、OPF 与正文继续读取，避免因标识损坏损失兼容性。 |
| 路径大小写 | 128 | 应当报错 | 变体只改 ZIP 内 OPF 路径，container 原引用没有同步，必需包路径按大小写精确查找时不存在。 |
| OPF 资源不存在 | 128 | 应当报错 | 本批改的是 spine 必需资源的 href，并非可忽略的未用资源，正文无法完整加载。 |
| 资源重复 | 128 | 应当报错 | 本批同时制造重复 manifest href 和重复 ZIP member，资源身份存在歧义。 |

八类结构错误合计 **1,024** 项；其中新定性的待查是 **184** 项。每条的样本 SHA-256、配方、具体原因、两档实测及结论见 [cases.jsonl](cases.jsonl)；184 项单独列于 [PENDING.md](PENDING.md)。

[OCF 3.2 规范](https://www.w3.org/publishing/epub32/epub-ocf.html#sec-zip-container-mime) 要求首个文件为 `mimetype`，内容为 US-ASCII 的 `application/epub+zip`，且不能压缩、加密或带本地 ZIP 头额外字段。新增接口检查这些结构约束，以及目录/本地头、CRC、唯一 member 名、容器、OPF/spine 和 manifest 的精确路径。

## 184 项为什么成功

### mimetype：128 项

此前没有校验，不是检查后决定宽容：默认 `epub_metadata` 从 `META-INF/container.xml` 开始读取，再读取 OPF，随后按需提取章节；它不请求 `mimetype`。本次把这种默认兼容行为与显式严格校验区分开。

### directory：56 项

不是“扫本地头”的恢复路径。生成器轮换修改**首个中央目录条目 mimetype** 的字段；成功项恰为 `local_header_offset` 19 项、`compressed_size` 19 项、`uncompressed_size` 18 项。其他目录条目及其正文数据保留，mimetype 又从未被读取，因此正常遍历成功。

默认 ZIP 打开依赖中央目录，损坏/缺少 EOCD 或无法解析的目录会失败；提取已请求成员时按目录给出的偏移读取一个本地头，再用目录的大小、方法与 CRC 取出数据。它没有遍历本地头来重建目录。实现依据是仓库的 `archive_open` / `archive_backing`、`member` / `epub_parse_chapter`，以及依赖 [miniz 3.1.2 的提取与校验实现](https://github.com/richgel999/miniz/blob/3.1.2/miniz_zip.c)。

具体边界：

- 只破坏未请求的 member，默认可能成功；本批 56 项属于此情形，不能据此推断正文错误。
- 请求成员的偏移指向非本地头、数据越界、解压失败或内容 CRC 不符，会失败；本地头的文件名并不在普通提取路径中核对。
- 如果目录将 `OPS/main.xhtml` 指向另一个有效本地 member `OPS/evil.xhtml`，并同步目录 CRC 和长度，默认能返回替换后的正文而不报错。新增回归直接断言读出 `Replaced text`，严格模式则明确拒绝本地文件名失配。这是可构造的内容身份错误边界，不是这 56 项已经发生的行为。
- 严格模式遍历所有目录条目，核对本地头名称、方法、flags、大小及 CRC；即使未被阅读使用，也要检查。空成员另查头部范围与空内容 CRC，避免依赖库跳过空文件校验留下缺口。

## 回归结果

| 验收项 | 实测 |
|---|---|
| 严格：应报错 / 命中 | **1,024 / 1,024**，八类各 128/128 |
| 原 184 项待查 | **184/184** 明确拒绝，其中 mimetype 128、目录 56 |
| 宽容：原“通过”项仍通过 | **840/840** 仍有明确错误文本并返回非零 |
| 宽容：接受项 | **184/184** 仍完整读取；1,024/1,024 项的返回码、状态、完整遍历标记及错误文本有无与原报告相同 |
| 有效唐诗基线 | 两档都返回 0 并完整遍历 |
| 真书 | main 改前 **19/19** → 改后 **19/19** |
| 真书逐页比较 | 两轮均 **11,061 页、8,648,640 字形计数**，像素变化 **0 页**，页数/字形变化 **0 本** |
| ctest | **172/172**，原有 169 项 + 新增 3 组 |

新增三组是 `native-epub-strict-mimetype`、`native-epub-strict-directory`、`native-epub-strict-container`；已有 `native-document-probe` 增测文件 API 的 `--strict` 入口、中文路径、参数位置、有效包成功与错误 mimetype 的两档分流。目录组包含 CRC 损坏、正文重定向及空成员 CRC；mimetype 组包含错误内容、尾随换行、缺失、空内容、非首条、压缩与本地头额外字段。

五条实际错误文本抽样：

- `mimetype-001`：`Strict EPUB: member 'mimetype': expected 20 bytes 'application/epub+zip', found 32 bytes`
- `directory-001`：`Strict EPUB: member 'mimetype': expected to be the first ZIP member (local header offset 0), found central directory places it at offset 1`
- `directory-002`：`Strict EPUB: member 'mimetype': expected compressed size 21 (central directory), found compressed size 20 (local header)`
- `directory-003`：`Strict EPUB: member 'mimetype': expected uncompressed size 21 (central directory), found uncompressed size 20 (local header)`
- `container-001`：`Strict EPUB: member 'META-INF/container.xml': expected a readable container, OPF and unambiguous spine/manifest, found ZIP member missing: META-INF/container.xml`

[summary.json](summary.json) 汇总双模式数字；[CTEST.txt](CTEST.txt) 为完整本地测试输出；[realbooks.diff.json](realbooks.diff.json) 为官方回归驱动的逐书零差异结果。两轮运行身份与逐书计数见 [改前](realbooks-before-summary.json) / [改后](realbooks-after-summary.json)，完整逐页原始 JSON 保留在仓库外构建目录，哈希登记于 [PROVENANCE.json](PROVENANCE.json)。历史 `c665d1cb` 的 19 本也全部通过；其后 main 的排版修改使总页数变化，本次严格以当前 main `c9dfc6c1` 的新鲜构建作前后比较，没有改写历史基线。

## 复跑

本地 Release 构建，GCC 16.2.0、Ninja，依赖和 EXR 配置见 PROVENANCE.json。构建目录为仓库外 `../malformed-triage-build`，改前源码与构建为 `../malformed-triage-before` / `../malformed-triage-before-build`。

```powershell
cmake --build ../malformed-triage-build -j 4
ctest --test-dir ../malformed-triage-build --output-on-failure -j 4
python -X utf8 tests/triage_epub_corpus.py --engine ../malformed-triage-build/exreader-check-document.exe --font tests/fixtures/fonts/primary.ttf --output evidence/malformed-triage-20261107
python -X utf8 tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll ../malformed-triage-before-build/libexreader.dll --font ../EXReader-Windows-delivery-20261104/payload/Reader.otf --layout tools/regress/layout.json --workers 4 --source-revision c9dfc6c1 --output ../malformed-triage-build/realbooks-before.json
python -X utf8 tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll ../malformed-triage-build/libexreader.dll --font ../EXReader-Windows-delivery-20261104/payload/Reader.otf --layout tools/regress/layout.json --workers 4 --source-revision c9dfc6c1+malformed-triage-worktree --baseline ../malformed-triage-build/realbooks-before.json --output ../malformed-triage-build/realbooks-after.json
```

受保护树已登记于 [R-PROTECTED-TREES.md](../ci-packaging-20261103/R-PROTECTED-TREES.md)。未修改 examples/ 或 .github/，未手动运行 CI、未取消 workflow run。
