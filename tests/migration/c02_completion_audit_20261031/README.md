# C02 原始产物审计

仅在 GitHub Actions 执行此目录的 Python。需要 Python 3.12、Git、已按通常方式认证的 gh CLI，以及 contents:read / actions:read。脚本不会构建 SDK、改注册表或修复生产文件。

```sh
python tests/migration/c02_completion_audit_20261031/audit.py \
  --manifest qualification.json --output audit-evidence --require-complete
```

qualification.json 按 manifest.template.json 填入最终合格源码的真实 run、attempt、job、artifact ID、原 ZIP 字节数与 SHA256。模板的 null 必须替换。所有包必须属于同一 producer source。失败历史继续保留，不能将别的源码的绿步骤拼入这一份请求。

脚本依次保存每个包的 run.json、jobs.json、artifact.json 和 original.zip；核对 GitHub API、指定 attempt 的作业与上传时间、ZIP 字节数和摘要。随后在内存读取原 ZIP，验证路径、CRC、完整文件清单和内部语义。结束时重新计算保留的每份 original.zip 摘要。运行失败时也应使用 workflow 的 always() 上传整个输出目录。

## 已实现的协议

- Windows / Linux 原 ABI2 都要求 81 项、准确六行已知失败、原始 exit=1；ABI3 都要求 16 场景 / 64 项 / 0 失败。
- Windows 原生日志要求 46 场景 / 301 项，十个原生进程 barrier 与原始 46 对 journal/intent。独立重算完整事件 FSM、行 seal、BEGIN/ACK 哈希链、manifest、连续旧 count 和完整 tip。
- 持久 gate 要求原 28 场景 / 309 项、四个进程 barrier；独立解码原始 344B gate 记录，包括保留的损坏负例。
- Registry 要求请求中明确指定的最新案例数与检查数，保留 50 / 530 下限；逐项核对 11 个准入命令场景和 6 个真实 Windows 产品场景。
- read-only scanner 核验请求中的最新 cases/checks/observations（当前29/91794/6603），逐条重建6603份带SHA的输入观察，并独立拒绝保留的19份完整语义负例。它仍是组件证据，不冒充生产修复。
- 原迁移器回归必须执行对应源码的全部 @case 场景，逐项检查每条断言。
- 实际迁移案例数来自对应源码的最终 len(r.rows) 断言，不固定为历史 25 项。逐案例核对 barrier、被终止的进程、命令退出码、注册表导出的 INPUT / PREPARED、实际原始文件、保留旧产物与最终数据库和账本。provider 文件清单逐项与 producer source 的 Git 内容核对；只接受 Git blob 字节或 Git checkout 的 CRLF 形式。
- 实际 journal 切点要求 phase 1..10 × sequence 0/5/9/10。repair 切点由 required_repair_phases 指定，目前必须包括 950..955 × 原始 sequence 0/10。还要求 gate 短写 201/203 和 repair archive 字节 / 身份拒绝两例。
- 独立解码 WH3RPR01 修复计划，核对 INPUT 权威、封存三份原始字节、最后完整 ACK 前缀、计划 gate、修复历史和退休状态。额外核对225字符真实root，以及保留FileID将当前完整ACK9回退至ACK5时的拒绝和原文件不再改变。候选下一行由 INPUT 的原生对象、快照 / 内容摘要和完整 FSM 独立推导，不能跳过一个完整 ACK。
- 使用 Python SQLite 的内存 deserialize 与 query_only 直接核对实际数据库：应用与 schema、原文、内部账本与外部 mirror 原字节、reflow / fixed / audio 批注，并核对唯一引用与歧义引用两个独立 TXT 场景。没有导入生产 verifier。

## 尚需各平台接入的 adapter

现有 Android / macOS owner 工件只有 build receipt，因此会记录 build-only 并留下缺口。host-gtk 也必须提供实际工件。没有这些证据，默认审计退出失败，full_c02_complete 保持 false。

未来运行报告可通过每个 host 包的 admission_report 和 observation_log 接入，格式：

- 报告 schema 为 c02-host-admission-v1，含 source/run/attempt/platform、actual_sdk:true、complete:true、passed:true，以及 cases 数组。
- 必须有 clean-admits-before-sdk、pending-refuses-before-sdk、missing-binding-refuses-before-sdk、last-borrow-blocks-owner、final-borrow-release-allows-owner、fresh-process-pending-refusal 六个唯一场景。
- observation_log 每条原始记录为 C02-HOST-OBS 后跟 JSON。cases[i].observation 必须等于同名原始记录。
- clean 的 sdk_open_count 必须为 1；三个拒绝场景必须为 0 且 admitted:false；最后 borrow 存活时 owner_admitted:false，最后释放后为 true。

此接口目前只核验运行观察。各平台真实 authority 的原始文件协议确定后，仍须在 host_evidence 中接入原生状态解码，才可消除 native-authority-semantic-adapter 缺口。不能仅靠补这六条 JSON 宣称完成全 C02。

实际迁移 runner 的成功 detail 应包含 evidence_dir（相对 actual-migration/cases 的目录名）。二次修复进程案例还需 repair_phase、repair_owner_exit、origin_phase、origin_sequence；原始日志分别为 killed-owner.log / repair-owner.log。篡改案例保存 prior_stage / after_stage 的 dev、ino、sha；repair archive 拒绝案例保留 raw_before 三文件摘要。新增未知协议应补 decoder，不得删掉缺口判断。

## 重新封装负例

从已通过的 Windows 原 ZIP 文件集生成 9 份新的 ZIP。每次都重新生成文件清单、文件摘要、ZIP CRC 和新 ZIP 摘要；内部 BEGIN/ACK 篡改还重新计算记录 seal 与后继链。包括 source/run/attempt 重绑、假 full-P0、保留字节、重复旧 count、错误 ACK 绑定、内部行损坏、降低原 301 项计数。每份新 ZIP 与拒绝原因均保留，原 ZIP 不变。

只有明确检查当前局部证据时才使用 --allow-incomplete；其输出 scope 为 component-evidence，缺口原样列出。完整验收使用默认行为或 --require-complete。此脚本不会更新正式 95/108，也不授予 F12 / 全 P0 验收。

## 独立 Actions 入口

workflow 为 .github/workflows/dot-c02-completion-audit-20261031.yml，每个作业最多15分钟，contents/actions均只读。audit代码始终checkout本次运行的github.sha，并核对本地HEAD；producer source独立固定，不会把audit提交当生产提交。

默认 push / dispatch 选择 windows-components，仅允许 qualification.windows-faae.json 已固定的 faae61879441085d800879332699d0b6fd5e2307：原Windows/Linux native包、persistent gate包、Windows registry/83项真实迁移/scanner/CLI/host包。四包的run/attempt/job/artifact ID、字节数和SHA均写死，并再次经API校验；组件模式保留full_c02_complete:false。

dispatch输入：
- producer_source：完整40位生产提交SHA，默认上述faae提交。
- scope：windows-components 或 complete-c02。
- qualification_manifest：仅complete-c02使用，填写完整JSON请求；必须包含七种包角色并与producer_source相同。

组件模式拒绝传入自定义manifest或更换producer_source。完整模式使用--require-complete；各平台native authority解码尚未完成时会明确失败。工作流先在Actions做Python语法检查，始终上传准备日志、API响应、已下载的原ZIP、失败输出、最终scope与摘要清单。

示例调用（workflow发布到可dispatch的ref后）：
```sh
gh workflow run dot-c02-completion-audit-20261031.yml \
  --ref codex/dot-c02-native-journal-20261030 \
  -f producer_source=faae61879441085d800879332699d0b6fd5e2307 \
  -f scope=windows-components
```
