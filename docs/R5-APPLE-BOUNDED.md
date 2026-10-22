# H9 Apple 有界 EPUB 候选

本包在 `fd210224a4eba206762c08de435a5e9edfdf2a90` 上准备 Apple 局部实现；
原SDK基线为`ce5d664c9f76d0613df6d79b27568a7039c4a81e`。Repeated边界诊断暴露同root下降循环后，
现合入修复候选`2f26847684b54006ca812c35477ceae43719e7d4`；SDK六组18作业重冻结与Apple八作业并行复验。
工作流逐项拒绝与该候选的受保护SDK树差异，并把基线写入三SDK身份、严格汇总及拒绝回归。
候选未获验收。构建、Swift 编译、夹具生成、测试与证据计算只在 GitHub Actions 执行。

## 路径

新 EPUB 通过 FileHandle 随机 source 导入 SQLite；publication 从书库 source 打开，保持稳定取消上下文。
每章使用 bounded pager，保留两页/8 MiB 缓存与4个/2 MiB检查点，解析工作区16 MiB、窗口16 KiB。
UI只拥有当前页图像和最多2 MiB页文字，不保留 EPUB 章全文或全书快照。
part/path、章内 UTF-8 point 和同章 notes 使用 schema7 公共 API；旧memory模式仍走原global记录。
同 owner 更新保留source；外部SQL提交的source失效遵循SDK契约，失败不当作EOF。

前后翻页跨reading-order章节，重复path由part区分。新进度重开只将FOUND视作精确恢复；
未匹配/歧义保存记录保持原样，界面明确显示从章首浏览，显式用户移动后才保存新点。
异章notes先显示待定位，跳转时建立目标章pager并实际解析，只有FOUND发布页面。
选择上下文包含book/frame/part/path/章内起点；原生选文UI和原始UTF-8转换保留。

## 验收契约

原12 UI/61具名步骤/46附件、21legacy、21SDK桥接、18Model保持。
原Model数字回滚回归明确使用公开memory import准备legacy书，继续验证真正global写入。
新增三平台第13个UI用例、6步骤、3截图，覆盖source导入、跨章、notes跳转、重开、前翻。
新增macOS安装SDK消费者15项：source/模式/中途取消及晚到回滚、稳定取消owner、重复path、跨章、notesCRUD、
字号/窗口/重开、歧义拒绝、非法路由、原重复样本歧义、旧memory兼容、schema6升级原件/进度/notes保留、50MiB单章后段读取。
长章范围为首屏渲染与后段文字/章末point，不宣称全章分页或全局性能门槛。

原重复Sample保留为Repeated.epub负例；正例Sample使用独立编号语料，避免把真实歧义冒充精确匹配。
严格汇总继续绑定八作业/八工件同run/source/attempt，数据库必须schema7，逐书核marker/part/path/point/notes命名域，
host-state升级schema2并与SQL逐项比较。新增缺marker、缺point、错误路由/global冒充/错误note owner等拒绝用例。
进程RSS由独立消费者子进程的high-water采集，包含字体、accepted/candidate frame和分配器；编译器排除。

真机安装/签名、VoiceOver、全格式有界化与产品完成仍独立跟踪。`complete_product=false`。

## 保留的候选运行

`62b9d116ea046b6c3cc79babc6d87584272d163e` / run `39864500523`：三个SDK构建成功，
原SDK桥接21项与Model18项成功；新增bounded消费者编译失败，原始`compile.log`保留在package工件。
macOS与iPad各13UI/67步骤成功；iPhone12/13成功，原PDF选词后标注步骤失败，严格summary拒绝。
后继驱动在真实选词后明确用一次外部标签点击关闭UIKit编辑菜单，并继续核选中文本及原标注断言。
该候选未通过。后继将消费者的throwing短路表达式拆成明确的先取值后比较，并让编译失败诊断直接进入云端日志；
同时追加source中途取消/晚到回滚和schema6兼容检查。运行结果不拼接。

`86d5a53aa8c622b2936f519304698feb9363250c` / run `39865340346`：三个SDK构建成功，
三平台各13UI/67步骤成功，iPhone collector也为`accepted=true`；原SDK桥接21项、Model18项成功。
bounded消费者已成功编译，但900秒执行预算耗尽，package及summary拒绝；本轮未获验收。

`254ea3398097498f12719da3da6b981ada01fe60` / diagnostic run `39869222854`：
180秒隔离诊断的前11项成功，停在`original_repeated_fixture_refuses_ambiguous_note`，
50MiB长章尚未执行。该运行只定位失败，不授予Apple验收。后续诊断细分import/publication/pager/anchor阶段，
并以原Repeated夹具对照16/64KiB窗口；正式默认仍为16KiB，解析工作区16MiB与900秒预算不变。
非默认窗口证据明确标为`diagnostic_only=true`，不替代原负例或正式八作业复验。

阶段诊断`a77530d` / run `39869850934`确认Repeated已完成导入、publication与chapter-pager建立，
第一次`makeAnchor(1024,1088)`在180秒预算内没有返回；尚未进入selector解析。
同源对照`11d80be` / run `39870093796`中，16KiB窗口在相同阶段超时；64KiB窗口原负例2.28毫秒成功，
`windows_loaded=1`、`windows_evicted=0`，15项检查全过；50MiB长章首屏约1.43秒、整个长章检查约1.70秒。
这些是隔离诊断结果；正式窗口不扩大，SDK修复及重新冻结后的八作业复验仍待执行。

修复SDK候选`2f26847684b54006ca812c35477ceae43719e7d4`的Apple复验源码为
`86c3219f36501aa334c4ef6fc91b2efc5be000f5` / run `39871718040`，保持正式16KiB/900秒。
三个SDK与Swift预编译已成功，UI及package/summary仍在运行或排队。
SDK候选的新增预算回归随后仅修正触发时机，后继重冻结候选为
`9c69bc4c7efb0cff68ced27562709fe597189041`，其受保护实现树与`2f2684`相同。
本轮Apple先完成以定位剩余宿主缺陷；最终身份仍须与重冻结候选统一。
