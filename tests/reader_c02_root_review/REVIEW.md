# C02 root-review：最小输入状态适配方案

状态：三次新完整云端均为failure，预算已用完，已停止重跑。自然首屏及warm输入修正通过收据核验；最后一轮全部数值样本正常，
但GTK launch失败标记使原聚合拒绝，C02整体未通过。未运行本地语法/测试/构建，也未本地下载或处理工件。

暂停checkpoint `6a795c64` 保留断网前未验证草稿；用户已重连并授权继续最后第3轮。第二轮证据已在远端 `ff81936a` 封存。
恢复后完成源码审查：只新增9个自有文件，169的全部既有blob/mode未改；workflow仍精确投影原完整scope，
仅GTK入口新增旁观adapter。Windows原op_resume/op_page_turn只透传调用一次，保留原参数/返回值/异常与4forward；
GTK保留原scenario_import/turns、原Watch._loop/wait和180秒等原等待，将按键、原wait记录及独立inotify仅写入诊断。
所有诊断均在真实操作前后读取状态或旁观文件事件，可能增加观察者开销，未从样本中减去，不授予产品性能。
独立文件事件携带的是通知后最新快照，可能错过被覆盖状态；没有busy记录不能被解释为证明worker从未启动。
诊断不能修改原样本outcome、predicate、计划、聚合或预算；最后完整轮结束后不再盲目重跑。

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
  整轮最终failure，strict实际下载认证全部6个build/round ZIP后拒绝两轮Windows首屏收据。
  GTK round1另有真实采样失败：358 rows/6 non-ok，其中4项不被旧规则允许（3次import worker start超时、1次page turn超时），
  其余2项为原规则允许的resize not_observed；GTK round2为384 rows/0 non-ok。GTK原采样器未改动，也未把这些失败过滤掉。
- 第二轮 `40238597205/1`，source `bac5606fa8a6efa395a88c148b28ff25d52185ec`：
  源保护、协议回归和两平台重新构建通过，strict job `121311235125`认证6个实际同次ZIP，
  两个Windows round的30份输入/22份自然首屏/8份warm catalog收据均通过；全部cold/warm/import启动正常。
  Windows round1为1062 rows/15 non-ok：n5000 resume-02原翻页25秒无transition；随后resume-03恢复位置与旧expected不符。
  原逻辑只在四次forward均成功后更新expected，但close会保留已前进位置，因此第二个失配是连锁结果；首个超时原因尚未证实。
  长书为2000段，不能推断是页尾。Windows round2为1063 rows/0 non-ok，两轮各30 launches。
  GTK round1为364 rows/4 non-ok（2次import worker start超时、2次翻页超时），round2为376 rows/2 non-ok
  （1次import start失败及1次允许的resize not_observed），两轮各24 launches。
  strict按原规则拒绝整轮，`measurement_complete=false`。所有job/artifact ID、ZIP字节及digest见同目录validation.json。
  原sampler要求inotify观测到busy=1；当前证据不能区分未启动与漏观测，失败保留。
- 第三轮（最后完整轮）[`40243807845/1`](https://github.com/NoGod3524/EXReader/actions/runs/40243807845)，
  source `c86ddb57bfb3dd8ed7dc53cd07fcbfc94e95d32a`：源保护、协议用例、两平台构建通过。
  Windows两轮分别1057/1058 rows，各30 launches；GTK两轮各384 rows/24 launches；总2883 rows全部`not_ok=0`。
  strict `121323232484`实际下载并认证6个同次ZIP及完整bundle，核对输入/自然首屏收据、Windows每轮168份操作记录、
  GTK每轮24份timeline/16次导入busy等待。Windows无失败操作，16次恢复均与真实expected页面匹配；本次未复现此前恢复/导入超时，
  不据此声称根因修复。原watch捕获全部32次busy；部分独立通知后快照没有busy，说明这类最新快照的缺失不能证明worker未启动。
  最终仍为failure、`measurement_complete=false`：原聚合列出GTK r1的10个、r2的11个failed launch；全部GTK launch日志均exit=0，
  没有`LAUNCH-FAILURE`或数值指标失败。失败标记和零non-ok的矛盾保留，不把失败降级成not_observed。

## 第三轮关闭期诊断差异（纯源码对照）

源码审查遗漏了新增诊断对原failure读取时机的影响：

1. 原 [`observe.py:179`](https://github.com/NoGod3524/EXReader/blob/169b0be3c1c8199be0211649412d23d9e34041e4/tests/reader_perf_gtk/observe.py#L179)
   的`Watch.close`置running=false并关闭inotify fd，未join原watch线程；原`_loop`的select/read异常分支会写入`self.failure`。
2. 第三轮 [`gtk_adapter.py:66`](https://github.com/NoGod3524/EXReader/blob/c86ddb57bfb3dd8ed7dc53cd07fcbfc94e95d32a/tests/reader_c02_root_review/gtk_adapter.py#L66)
   在原close之后再等待独立observer退出（最多2秒），随后写诊断JSON，才返回原sampler。
3. 原 [`sample.py:709`](https://github.com/NoGod3524/EXReader/blob/169b0be3c1c8199be0211649412d23d9e34041e4/tests/reader_perf_gtk/sample.py#L709)
   随后才读取`watch.failure`保存到`observation_failure`；原aggregate第104行将该字段非空的launch判失败。

因此新增诊断扩大了原fd关闭后到failure取样之间的时窗；这是明确的执行时序差异。EBADF/关闭竞态是源码线索，
当前打印日志没有具体`original_failure`值，不能作为已证实的实际故障原因。工件保留完整original_failure与独立时间线，
后续由root安排实际sample closure修复及单独有界验收，本包不启动第4轮、不改变原failure语义，不冒称性能达标。

所有最终job/artifact ID、大小、digest与2027-01-23到期时间见`validation.json`。原summary工件保留CPU分层p50/p95/max及RSS，
预算仍为未批准的建议；本包只测旧Windows0889/GTK572 producer，不授予当前共同源码、完整产品或旧SDK预算达标。
