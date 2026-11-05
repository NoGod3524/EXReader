# Dot新一轮：独立验证与缺口收口

实现固定起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`。本批仅新增验证工具、消费者、工作流和文档；
实际受测宿主采用各任务页的固定目标源码。分别记录 harness/source/run/attempt 和 target/source/program，
不得把工具分支SHA写成另一checkout中宿主的SHA，不伪造GitHub身份变量绕过原guard。

SDK为批准3.41候选 `edddc463c06ed5731195cdb8f06b2df6dff7699e`；旧3.40冻结
`9854061be331fe603a1822d9b2b36ee357154927`、raw七模块 `56793e7c`、旧预算、schema1与旧wire均保留。
原owner、SDK、其他包、旧测试及旧裁判一律只读。发现真实产品缺陷交root，不在本包修产品来过测试。

每包独立worktree与 `codex/reader-dot-dNN` 分支，只写本页独占路径。共同起点是实现起点，
不是宿主已经实现全部目标的证明；目标分支的历史失败也不是本包可重新解释的结果。
可二次checkout或认证目标原工件，必须校验固定source/run/attempt/jobs、唯一ZIP、字节/SHA-256/有效期与实际程序。
ZIP默认可能丢权限/链接；原生产者没记录的属性只能pending，不通过chmod/重签制造原始身份。

所有构建、测试、语法、夹具、截图、benchmark及工件下载/解析仅GitHub Actions；本地只读写源码/文档/Git。
只使用runner临时测试资料与随机测试账号，不访问用户书库或真实凭据。TLS验证不得关闭。
无需再问是否push：自行推功能分支触发Actions；不开/合PR，不推默认分支，不打tag/Release，不使用cpuse。
不再派子代理；最多三次完整CI迭代，每次等待原轮terminal并按日志修根因。超限交回完整失败与下一步。

原断言不得变弱，无法观测不算通过，超时/崩溃不算正常拒绝。回退和注入仅能作独立诊断，不能满足验收项。
样本量、缺项、每项结果和实际原始值必须保存；汇总不得靠总数或任意JSON里的accepted字段授予范围。
模块、实际UI、自动化属性、读屏、真机、性能分别授予，不把功能可点击等同于读屏可用。

每包必须交完整受测/harness/target/最终文档SHA、run/attempt/jobs、原工件ID/bytes/SHA-256/expiry、实际程序hash、
具名完整检查集、旧失败、未验证项及root接入点。文档封存用 `[skip ci]`，只改自己的证据文档。
交回文件使用独占的 `HANDOFF-RESULT-DNN.md`，避免覆盖其他包。未执行前validation必须accepted=false。
