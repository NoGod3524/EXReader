# 真实文档兼容性验收（F5）

本包只补真实书籍/文档的**原生阅读结果**，不改引擎、不改历史检查器、不改旧预期，也不把差分参考
或格式 smoke 当作 EXReader 通过。固定起点为 `cdfe48231853d6e70fba2c41b42bdd187155901a`
（`codex/framework`），工作分支 `codex/reader-real-corpus`。

## 1. 所有权与不变量

仅新增：

- `tests/reader_real_corpus/**`（消费者源码、固定清单、协议自检、边界夹具生成器）；
- `.github/workflows/reader-real-corpus.yml`；
- `docs/READER-REAL-CORPUS.md`；
- `docs/validation/reader-real-corpus.json`。

仓库不保存语料字节。下载、清单冻结后的解析、逐项执行和工件上传都只在 GitHub Actions 发生；
输入、许可快照、逐文件/逐操作结果和汇总随运行工件保留 30 天。

## 2. 固定语料

九个公开格式各两份真实独立文件，共 18 份。每份登记源 URL、作者、出版信息、许可/公共领域依据、
精确字节和 SHA-256。SHA-256 先由云端 `pin` 作业下载后写入清单，经人工核对提交，随后
`accept` 作业只接受完全一致的字节；不符立即停止该项，不换 URL、不换样本、不接受新版内容。

| 格式 | 文件 | 作品/作者 | 许可依据 |
| --- | --- | --- | --- |
| EPUB | `pg11-images-3.epub`；`pg84-images-3.epub` | Alice / Lewis Carroll；Frankenstein / Mary Shelley | 美国公版 + Project Gutenberg 条款 |
| TXT | `pg1342.txt`；`pg2701.txt` | Pride and Prejudice / Jane Austen；Moby-Dick / Herman Melville | 同上 |
| HTML | `pg1661-images.html`；`pg345-images.html` | Sherlock Holmes / Arthur Conan Doyle；Dracula / Bram Stoker | 同上 |
| PDF | IRS W-9；NIST AI 100-1 | 美国财政部 IRS；NIST | 美国政府职务作品/公共领域；NIST 开放许可 |
| FB2 | `Turgenev_Bretyor`；`Turgenev_Tri-portreta` | И. С. Тургенев（1883 年去世） | 作者去世逾 70 年，公版；Internet Archive 转录 |
| DOCX | HMCTS Form ES1；MHRA response template | HM Courts & Tribunals Service；MHRA | Open Government Licence v3.0 |
| RTF | `PolicyandProcedure.rtf`；`MicroRepublic.rtf` | Professor Crowley；Sanford Staab | CC BY 2.5（源条目逐文件声明） |
| MOBI | `pg11-images.mobi`；`pg84-images.mobi` | 同上 Alice / Frankenstein | 美国公版 + Project Gutenberg 条款 |
| CBZ | `peppercarrot_episode01.cbz`；`episode02.cbz` | Pepper&Carrot / David Revoy | CC BY 4.0 |

缺失合法输入时必须在清单 `pending` 中写明原因，不能生成文件冒充真实文档；当前没有 pending。
合成/边界文件只出现在 `make_boundary.py` 的临时目录，永不进入 `files` 计数。

## 3. 逐项验收

消费者 `tests/reader_real_corpus/consumer.c` 只链接安装后的冻结 SDK
（`find_package(EXReader CONFIG)`、`EXReader::exreader`），按格式实际支持项执行：

1. 公开书库导入，并用 `exr_library_blob` 回读原件字节；
2. 公开重排/固定页接口打开；
3. 标题；PDF/CBZ 另读公开 metadata 条目；
4. 公开目录：EPUB 用 `exr_publication_navigation`，其余重排格式用 `exr_document_navigation`；
5. 初页/中间页/末页实际绘制；整本顺序遍历；后退一页；
6. 精确文本查找，真实锚点 capture，在同一文档 resolve；
7. 从同一路径重开、重新计量页数，并对重开后的文档再次 resolve 同一锚点。

固定页格式没有公开导航接口，记为 `not_exposed`；CBZ 的零文本是可说明的文档属性，记为
`empty`，锚点记为 `not_exposed`。这些边界在汇总中单列，不以“删除样本”或“放宽预期”消除。

## 4. 云端出口

工作流 `Reader real corpus` 仅手动触发：

- `mode=pin`：只下载并输出 `pin.json`（final URL、字节、SHA-256），不构建、不运行 SDK；
- `mode=accept`：先在 Ubuntu 跑协议负例，再在 Windows 与 Linux **同一源码**上分别
  构建并安装 SDK、编译消费者、下载冻结语料、逐文件执行；两平台结果都上传；
- `aggregate` 作业要求 Windows/Linux 两份 summary 的 source commit 与清单散列一致，
  且 18 份在两个平台都 accepted，才给出 `accepted:true`。

汇总按格式给出已验收/失败/pending 数，并保留逐文件、逐操作状态、程序身份
（SDK 版本、ABI、消费者散列、字体散列、运行/尝试 ID、清单散列）。任一下载散列不符、超时、
进程异常、读回字节不一致或结果与固定预期不符，整个批次拒绝通过，但其余文件继续采集。

## 5. 当前结果

首次 pin 与验收运行完成后在此登记实际 run/attempt、工件 ID 与 SHA-256；在结果出现前，
`docs/validation/reader-real-corpus.json` 保持 `accepted:false`。本包的 18 份不计入旧
1710 目标，也不改变 1710 的历史完成数。

## 6. SDK 问题上报

发现 SDK 问题只提交最小复现：公开输入身份（清单 id、字节、SHA-256）、操作、现象、期望与建议；
不改冻结源码、不粘贴崩溃栈或攻击细节，由 root 决定修复或重新冻结。修复后仍需同一清单、同一
预期、同一源码在 Windows/Linux 完整重跑，不能拼接旧通过项。
