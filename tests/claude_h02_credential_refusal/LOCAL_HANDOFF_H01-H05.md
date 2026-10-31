# EXReader H01–H05：交给本地 Claude 客户端的交接书

把本文件整体粘贴给本地 Claude。云端会话停止后，由本地接手；两边不要同时写同一分支。

## 先做的三件事
1. 在云端会话里确认 H02 的 run 41142963420 / 之后的 run 已结束。
   在 GitHub 上看分支 `codex/claude-h02-credential-refusal-20261030` 的最新 workflow。
   运行中的作业不要重复触发。
2. `git fetch origin` 后核对这些完整 SHA（不要凭克隆里有没有对象判断远端是否存在）：
   - H01 输入：`codex/p0-win-restart-reader-20261030` 上的 `6db7c3dc1005c7fd22f91b02a150bfdd671f723c`（是该分支头 `638976413692412fd7cc15d7e508d0382d1faffd` 的祖先）
   - H03 输入：`codex/dot-f05-paging-evidence-20261030` 的 `7f15fe49374cd9389e2106837351d4bbd5e56113`
   - Apple 避让（只读，不修改）：`codex/dot-apple-query-observation-20261030` 的 `8ec841fe5127b810ad37f14662de51650c0b51c2`
   - 冻结 C01：`ccd7fec67eb8aa463b09533ce320820f2da472d9`（远端分支 `claude/dot-p0-lease-20261030`）
3. 从云端已推送的 H02 分支读 `docs/CLAUDE-H02-CREDENTIAL-REFUSAL.md` 和运行日志，接着做，不要重写。

## 共同边界（用户已批准的通道）
- 所有构建、语法检查、测试、fixture、benchmark、工件解析只在 GitHub Actions 执行，不在本机执行。
  本地只读文件、写文件、提交、推送，并用 GitHub 工具触发和读取 Actions。
- 只允许五条分支：
  `codex/claude-h01-domain-gate-20261030`、`codex/claude-h02-credential-refusal-20261030`、
  `codex/claude-h03-original-retry-20261030`、`codex/claude-h04-anchor-evidence-20261030`、
  `codex/claude-h05-composition-audit-20261030`。
- 每个包只新增自己的 `tests/claude_h0N_*/`（H01 另有 `extras/migration/claude_h01_domain_gate/`）、独立 workflow、`docs/CLAUDE-H0N-*.md`。
- 不改 SDK、冻结 C01、生产 owner、旧测试、主线；不开 PR、不打标签、不发布。
- 不接管他人工作。避让：Apple `8ec841fe` / run `41139685986`；C07 审计 `2938e0af` / run `41139877482`；
  GTK 正常 restore-recovery 10 例；C02 native-journal adapter 的七个独占文件。先复核最新状态。
- 源码写入全局单写者：同一时间只写一个包。
- 每包最多 1 轮初始 + 2 轮修正验证。到上限就交失败证据和下一步。
- 异步取原 PID，不重复未明操作。遇到五小时额度限制就停止，观察到可用额度再恢复。
- 不得读取或导出凭据；不枚举用户凭据库，只扫描本包的合成标记。
- 每包交付：源码/文档 SHA、分支、run ID + attempt + job、工件 ID/字节数/SHA256、保留的失败、
  已验证和未证范围、复验命令。不拼接不同轮次成一次完整通过。
- 默认都是候选证据，不加分。正式验收基线仍是 95/108（87.96%）。

## 当前状态
### H02（已开始）
- 分支 `codex/claude-h02-credential-refusal-20261030`，当前源 SHA `2187d102148961eec66b06333d7797cf3e965055`，基线 `bd28d49`。
- 第 1 轮 run 41142853013：探针因 ctypes 64 位句柄签名缺失失败（我方 bug）。
- 第 2 轮（修正 1）run 41142963420 attempt 1：
  - 探针 job 124361348955 通过，工件 13019176825（832 字节）：NETWORK 登录主 token，session 2；
    同 token 下 CredWriteW/CredReadW/CredDeleteW 均为 1312；用 CreateProcessWithTokenW 启动。
    CreateProcessAsUserW 与设置 token session 因缺特权返回 1314。
  - host job 124361515465 配置阶段失败：复制的旧构建配方要求 OPDSHash 前缀，已过期，无工件。
- 修正 2 已推送（源 `2187d102`）：改用 `tests/windows_sdk342/build.py` 构建，导入走 compact picker。
  这是 H02 最后一次修正轮。结果见该分支最新 run。
- 已知局限：host 不暴露凭据返回码，worker 内部原始 1312 不能直接观测。
  证据链是 host token 为 Network + 无 impersonation + 同 token 探针 1312 + host 界面 UNAVAILABLE。
  若要直接观测，需另行授权在 `acct_set_job`/`acct_load_job` 加可选诊断钩子。
- 读码预判（待实跑验证，不是结论）：`acct_set_job` 在 put 失败时不清除旧内存 secret，
  场景 S3（A 在内存、保存 B 失败）可能红。红了就保留，不改产品、不弱化断言。
- 注意：云端曾在本地跑过一次语法检查，违反约定，没有产生证据；请不要再这样做。

### H03（只读已做）
- `examples/linux/metadata.inc`：初次 Restore 在 `metadata_save` 里校验保留原文件
  （`reader_catalog_sdk_original_identity`，digest 和字节数必须匹配）；
  Retry 直接调用 `reader_metadata_finish_pending`，GTK 层没有再验证。
- 需要先读正式契约，区分「仅恢复元数据」与「承诺恢复可解析原文件」，不要预设这是漏洞。
- 基础测试可参考 `tests/linux_host/check_metadata_ui.py`。尚未写任何文件。

### H01、H04、H05
未开始。H05 依赖 H01 的可执行 gate 和 C02 作者的已提交源码与工件；等待期间只做协议审查和审计器设计。

## 建议顺序
H02 收尾 → H03 → H01 → H04 → H05。
