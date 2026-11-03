# 本机路径脱敏

本次为新提交，不 force push、不 rebase 已推历史。扫描现有已跟踪 evidence 发现 34 个命中文件，包含指定的两份 provider-source 日志，均已在当前树脱敏。
仓库根替换为 `<worktree>`，其他用户目录前缀替换为 `<local-home>`，剩余用户名替换为 `<user>`；保留后续相对路径、文件名和退出码。

`files.json` 记录原文件和脱敏副本的 SHA-256。脱敏日志不再声称与原始输出逐字节相同；二进制与原始 ZIP 的身份哈希保持原义。
顶层 `artifact-sha256.json` 更新为当前提交副本的哈希；四态记录中的日志哈希同步更新。

通用 CI 规则交给 `../ci-hygiene-CI-ADMISSION-001/P_CI_HYGIENE.md`，范围为已提交 evidence 和 docs；本次不实施 P 的检查器或 workflow。
指定 evidence 路径扫描须无输出；命令的退出码 1 表示没有匹配。Markdown 保持 LF。

只修改 evidence，不改 catalog、代码、断言、SDK 版本或默认分支，不运行 CI。
负例验证仍阻断 R，随 R 候选轮验证。
