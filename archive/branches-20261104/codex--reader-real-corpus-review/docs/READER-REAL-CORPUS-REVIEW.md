# F5 独立接续审查

原交付分支 `codex/reader-real-corpus`、文档 HEAD `e9751245` 保留；
受测源码 `278d6369` / run `40067425188` 的结论为拒绝：Linux 14/18、Windows 12/18。
RTF、CBZ 和 Windows FB2 失败不转换为预期拒绝，也不替换文件。

原作者起点为 `cdfe4823`，没有使用交接指定的 `c3511a01`。审查分支从产品候选
`f1e7485f` 正常合入原交付，保留两条历史，并在云端强制核对指定祖先、冻结 SDK
`9854061b` 的八条保护路径、产品 schema 和本包改动路径。

## 消费者查询边界

原 Windows 消费者虽然使用 `/utf-8` 编译，仍通过 MSVC 的窄字符 `main/argv`
接收 Python 传入的查询。源码字符集设置不改变 Windows 命令行到窄字符 argv 的转换。
审查改用 `wmain`，将实际 UTF-16 参数明确转换为 SDK 要求的 UTF-8。
判定器另要求 SDK 消费者报告的查询与冻结清单逐字相同，拒绝查询已损坏的测试结果。

Actions 将重新核验原 Windows 工件的 SHA-256/大小，记录两份 FB2 实际查询的摘要，
这一步只有 `diagnostic_only=true, accepted=false`。run `40070449808` 的云端诊断
已确认原两份 FB2 查询均与清单不同；修正后，同次 Windows/Linux 两份 FB2 的
查找、锚点 capture/resolve 与重开全部通过。

SDK 构建改用现有 `reading-library` preset，消费端要求精确 3.40.0/core/pdf/library，
拒绝音频、PDF 编辑和全文索引组件。原清单的 18 份字节/散列/预期、18 项协议检查和
三个独立边界夹具保持，另加查询完整性的两项协议检查。边界失败不再允许忽略。

## 复验结果

受测源码 `80946aa4e16ef708c47d01252cb6c129d5d3af25`，
[run 40070449808](https://github.com/NoGod3524/EXReader/actions/runs/40070449808) attempt 1。
祖先/SDK/schema/路径守卫通过，协议20/20，Windows/Linux 均14/18、各三个边界夹具干净拒绝。
两平台共同通过 EPUB/TXT/PDF/HTML/FB2/DOCX/MOBI 各两份。

RTF 与 CBZ 各两份仍失败，两平台作业和 aggregate 均如实返回失败，
`accepted=false`。SDK 源码与冻结树逐字相同；未修改 `exr_document_find`。
作业、工件大小/散列/有效期见[审查记录](validation/reader-real-corpus-review.json)。

RTF 解析与 CBZ 路径策略需要独立兼容性评估。当前审查不放宽归档路径或输入校验。
本包仍未验收，18 份不计入旧 1710 目标。
