# C02 root-review：最小输入状态适配方案

状态：root 已批准以下方案，adapter、严格入口与拒绝用例已实现；首次完整云端暴露初始化误拒绝，已修正，待下轮完整验收。未运行本地语法/测试/构建。

## 依据与起点

- 正式任务卡：`c83ab05fa978c140afc4f4ec22b6cbb2ade5386b:docs/handoffs/reader-final-wave/C02.md`。
  要求实际 Windows/GTK UI、独立两轮、500/5000书架、身份/原始样本/分层统计；禁止改旧 SDK 预算。
  它没有冻结 prototype 的共享 warm profile 策略。
- 本独立分支基于原失败 source `169b0be3c1c8199be0211649412d23d9e34041e4`。
  旧 Claude 工作区及分支不改动。已只读比较其当前 HEAD `8796812478b01cb965338103260a19d143463010`：
  warm 改为已建 catalog + 干净 settings 的副本、launch等待改600秒、resume改前2后2、增加逐launch落盘。
- 诊断封存 `fd03b888f318136c74b4344efff1c3b339f94b34`；实际诊断 source
  `5dc9ad0612f80dc0a94e2879bb770538b6bfc978`、run `40230793806/1`。
  原EXE只观察6.219秒，稳定1行过滤能让原谓词无限等≥50行；清过滤恢复通过。
  compact阅读中隐藏的100行后台书架也能让原谓词通过。原报告及派生字段早期取样错误均保留。

## 最小修正

1. **明确 warm-catalog 输入，不再称连续共享会话。** 新 `windows_adapter.py` 继承冻结原 `Round`，
   只覆盖 warm 的输入准备：每launch从原 unmeasured template复制已建 product catalog/SDK书库，
   去除新私有副本的 `host.ini`、旧应用日志。不得写SQL、调用修复私有schema或改旧profile。
   记录模板/catalog的真实SHA、相对profile路径、copy策略、干净settings证明；准备发生在进程计时起点前。
   每份样本/identity/plan绑定 `warm-catalog-snapshot-clean-settings-v1`，与旧 shared-warm-profile 失败分开。
   复制会影响OS缓存，明确 OS disk cache/background load 未控制，不称受控缓存热启动。
2. **自然首屏，不在startup发Back或清搜索。** cold/warm/import在原 `op_window` 后，
   等待自然显示的主窗口/书架可见、阅读页隐藏、query为空；然后完整调用原行数/ready/roundtrip谓词，
   返回前再验证一次同样的可见性。保留首次真实 `op_window` 的映射时间，rows/interactivity仍从真实 `host.t0` 算起。
   不用后续UI切换制造首屏，不接受隐藏书架的后台行数。
3. **已知矛盾具名失败。** 干净settings输入出现非空query、真实阅读页前台等已知矛盾，立即产生具名
   `MeasurementFault`；原launch保存失败，缺失指标仍由原逻辑写missing。初始化按钮enabled和部分行数不作为完成信号，
   `>=50` 产品行/ready判定仍完整交给原helper，不因加载中的零行或部分行提前拒绝。
   失败不转为成功、不吞样本、不靠延长等待或降低旧SDK性能阈值。暂不引入879的600秒改动，先保持原deadline常量。
4. **保留169的resume与全部采样计划。** resume仍用独立reading profile，真实恢复后四次forward，
   不引入前2后2，也不把方向不同的样本混在同一“下一页”解释下。cold/warm各4、resume4、import3，
   两个规模、两轮、原指标/页数/CPU分层/nearest-rank/RSS定义均保留。
5. **逐launch保存原始结果与输入收据。** 通过自有adapter在原launch返回后落盘现有rows/launches/memory/plan、
   新输入与首屏可见性收据，再更新原bundle。失败/中断留下部分真实数据，原聚合仍要求完整规模、两轮及全部计划。
   新strict先核对策略、模板身份、天然可见首屏和每launch收据，再完整调用冻结原聚合/身份/ZIP认证；不改旧裁判。

## 预计自有路径与审查点

只新增 `tests/reader_c02_root_review/` 的adapter/source guard/receipt负例/严格入口与本说明，
以及独立 `.github/workflows/reader-c02-root-review.yml`；169的所有既有blob/mode保持不变。
新workflow逐字投影原完整C02，只换独立入口/分支与新增自有云端协议检查，保留两个平台的真实完整scope和原工件角色。
Windows producer/apps仍绑定原固定0889树，GTK producer仍为57203a52的另checkout；各source/程序hash分别记录。

源审查先确认：warm有catalog而非cold重建；settings清理只作用于新CI私有副本；startup无Back/查询修改；
原helper/host/预算/四次forward/计划常量无差异；可见性收据拒绝隐藏书架；旧shared策略与新catalog-copy不混身份。
所有协议负例、语法、夹具、UI、benchmark和工件解析只在Actions；最多进行三次新完整云端轮，失败记录保留。

## 新完整云端历史

- 第一轮 `40236796245/1`，source `1054892f9857abe2fb3e74cbbec5c8821522a53f`：
  源保护、原工具自检、新协议用例、Windows/GTK 构建均通过。Windows 两轮各保留30个launch、990个计划样本；
  各22个首屏launch被新增 `C02_READY_UNFILTERED_SHELF_TOO_SMALL` 过早拒绝，910个指标如实记为missing；
  8个resume launch正常。原进程退出状态不代表样本验收通过。
  `CreateWindow` 创建的按钮初始enabled，实际 `ShowWindow` 后才 `reload_shelf` 并启动product修复；因此初始enabled/零行
  或部分行不能证明加载完成。本分支删除了这项代理谓词，继续完整调用原>=50行/ready判定，只保留query/reading真实矛盾。
  新的协议用例明确要求hidden、零行、1行、legacy、disabled初始化均不得被当成完成后的矛盾；失败surface也逐次保留。
