# 兼容语料：冻结清单与云端验收

本包复用 `tools/check_corpus.py` 和 `tools/triage_corpus.py` 的逐进程检查及附件校验。
不修改引擎、原检查器、历史结果、原生CI或可靠性长测。所有生成、检查、收集和重跑在GitHub执行。

## 格式口径

以 `include/exr/base.h` 的公开 `exr_format` 和 `src/formats.c` 的实际分支为准。
PDF至少1000份、EPUB至少500份；TXT、HTML、FB2、DOCX、RTF、MOBI、CBZ各至少30份，
合计至少1710份**不同内容的真实文档**。原目标见 `docs/HANDOFF.md`。

HTML/XHTML共享EXR_HTML；MOBI/KF8共享EXR_MOBI。清单分别记录内容变体，
`.htm/.html/.xhtml` 或 `.mobi/.azw/.azw3/.prc/.kf8` 不是额外格式计数。
相同SHA-256跨路径、别名、格式或变体不能重复充数。变体覆盖明细单列；本包没有新设变体数量目标。
图像子编码和WAV/FLAC/MP3/AAC/M4A/M4B不属于该文档检查器的覆盖范围。

## 当前库存与历史结果

| 项目 | 历史输入/结果 | 本包可在云端复现的已登记真实资产 |
| --- | --- | --- |
| EPUB | 500份；483完成、11超时、5资源限制、1参数状态；原批未验收 | 0 |
| PDF | 122份；49完成，其余73份保留独立分类；原批未验收 | 0 |
| 其他7类文档 | 不能从现有证据推导真实语料数量 | 0 |
| 仓库原创夹具 | 可用于协议与原生进程自检 | 合成，计入真实目标为0 |

历史记录仍在 `docs/validation/2026-10-20-corpus-performance.json` 和
`docs/validation/2026-10-20-wp6-compatibility.json`，原预期、原路径和失败类别不改。
Gutenberg历史批有美国公版声明及原书条款，不等同于已完成逐文件跨地域分发审查。
历史外部PDF没有通过本包逐文件再分发权限审查；不读取、复制或上传它们。
仓库没有受版本管理的 `tests/corpus/manifest.json`。不把旧本地资产、历史完成数或合成夹具算作云端新增通过。

`tools/compat_corpus/manifest.json` 是空的待收集库存，`complete:false`。
它永远保留为本批库存快照。实际资产必须另建 `tools/compat_corpus/datasets/<dataset-id>.json`，
提交到Git后才可执行。已有数据集路径不允许改预期后再登记；新增数据集不得丢弃已有失败来替代旧验收。

## 清单协议

`schema:1`；`dataset_id`稳定；`targets`必须等于上述9类政策，不能为小样本降低目标。
`selection`记录预定选择方法、完整`candidate_ids`、`engine_results_used:false`及全部`excluded`。
排除只允许有证据的`permission_unconfirmed`或`not_declared_format`；引擎失败不能成为排除原因。
每个候选必须出现在文件表或排除表；每个已登记文件必须执行并保留结果。

每个`files`条目需要：

- `id/path/sha256/bytes/format/variant/kind/scope`：规范相对路径、内容身份、规范格式及内容变体；
  `kind`为`real`或`synthetic`；`scope`为`supported`或`boundary`。
- `source.url/creator/license/origin`：HTTPS源、作者、许可，以及`published_document`或`original_test_fixture`。
  原创测试夹具不能标成真实出版物。仓库级许可证不能自动授权第三方嵌入文档。
- `source.permission.redistribution:true/scope/reviewed_by/evidence_url/evidence_path/evidence_sha256`：
  对应文件的明确分发审查与许可原文快照。收集器同时下载并核对许可材料和原文。
- `expected:{status,complete}`：在观察结果之前声明。支持范围要求`status:0,complete:true`；
  边界拒绝要求非零状态、`complete:false`与`expectation_reason`，不计入真实支持样本数量。
- `capabilities:{open,render,extract,save}`与`save_reason`：支持样本前三项为`complete`；
  本检查器不验保存，`save`只能为`not_evaluated`。边界拒绝的前三项也不授予完成声明。

已有收集器保持原样：`tools/fetch_corpus.py` 的仓库级许可备注不足以直接升级为逐文件分发审查；
`tools/fetch_gutenberg_corpus.ps1` 的目录/RDF策略可供后续制订预选名单，但历史输出不得自动变更为新预期。
新工具不自动把观察结果写入清单，也不依据原生检查结果筛选来源。

Git第一次加入数据集清单的完整提交SHA是登记锚点。执行时必须提供该SHA，工具核对它是当前源码的祖先、
登记清单字节与当前字节完全相同、登记确为该路径首次加入、源码无已跟踪修改。
这提供可审查的预声明证据；来源和许可真实性仍需相应审查人根据原文确认，字段本身不代替审查。

## 云端操作

`.github/workflows/compat-corpus.yml` 只在本包分支及本包路径推送时运行协议自检，
单个Ubuntu作业只构建现有文档检查器，不触发96分片可靠性活动。
手动触发同一工作流时可提供已提交的`manifest`与首次`registration`提交SHA，执行受控收集和整批检查。
`resume_run/resume_attempt`可从同仓库旧云端产物恢复收集目录；没有本地转移步骤。

收集逐项记录`collection-attempts.jsonl`，请求间隔至少500ms，单个输入按已声明字节数有界下载，
许可材料最多4MiB；SHA或长度不符不发布。已完成文件续跑重新核对SHA，失败和部分下载全部保留。
中断的`.partial`不会静默覆盖：须在云端独立审查/归档后，再恢复原清单。
许可未确认的外部文件不能放进公开仓库或云端输入。

每次检查使用含运行ID/attempt的新输出目录；原 `check_corpus.py` 每个文件独立进程，
不提供文件数/页数过滤参数，逐文件完整记录日志、状态、源身份及散列。
输出与输入/许可/原声明再次校验，结果缺失、日志变化、跨源码结果、超时或预期不符均拒绝。
历史产物和本次产物独立，不能用新源码结果覆盖旧源码失败。

`pipeline_accepted`只在数量、许可、全部声明、完整收集和全部原生结果满足时为真。
`accepted`仍为false：全体验收还需要逐能力的保真与保存证据，以及规范矩阵。
自检成功只证明协议和失败拒绝路径工作，不授予语料或WP16验收。
成功/失败产物均上传，保留30天；发行归档须在到期前保存至项目约定的长期存储。

## 未完成项

1. 云端实际登记的真实文档仍为0；缺PDF1000、EPUB500、其余7类各30。
2. 按许可和公开来源选定全部候选、审查逐文件权利，并在运行前提交完整期望。
3. 用新鲜云端产物对当前源码重跑全部文件，保留原全部失败，不能改预期换取通过。
4. 像素/语义保真、保存/回读、PDF/EPUB规范条目矩阵，以及音频和图像子编码的独立验收。

本包不把素材缺失包装成收集完成，也不把历史500/122结果转授给当前源码。
