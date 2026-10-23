# R6：阅读SDK门禁与发布接线

起点`9bd2b2c3caf1f63dc4437e0af978247494e87145`；既有SDK冻结与四宿主结果保留在
[冻结记录](R5-SDK-FREEZE.md)。R6接线不改变公开API；集成分支同时纳入R2/R4核心修复。

## 当前收口状态

新SDK已在`9854061be331fe603a1822d9b2b36ee357154927`重新冻结：
六组18执行作业、30工件全部同源、attempt1通过，版本/ABI/schema保持3.40.0/1/7。
八份固定真实语料在该SDK上full8/8与location8/8通过；对应JPX专项当时失败，整run仍记失败，
后继同保护树源码da1c183的JPX最终契约run39899523839三作业全部通过，
原八份full8/location8也在该次普通ON作业重新严格通过，见[最终记录](validation/reading-jpx-final-da1c183.json)。

四宿主在共同S=`da1c1833d89932612d8e4549fee5aec378555ad4`重新复验，
Windows/Linux/Apple/Android分别为39899820869、39899823392、39899825998、39899828858。
本轮守卫已指向新K，Android所有权祖先以merge保留。
Windows/Linux已严格通过；Android原45中的pdf_process_restart帧比较失败，最终拒绝，
其独立10与bounded11通过不替代原出口；Apple因iPhone首次导入未触发而失败、summary拒绝。
两份原失败均保留。Apple一次标准tap修正已在run39903016234完整复验，
Android则在run39903068530加入DEBUG位图身份观测以定位299个±1边缘像素差异；原判定保持。

正式R3基线`887e1bb59ef6f28c15824cb7593654f3610f3cef`、run39899829270已完成40进程及12参考页。
逐页实际审阅后由云端导出数值预算，固定于`11cb054…`。该源码的run39901084062中，
包括严格performance的16个上游作业全部成功；performance确认accepted=true、measurement_valid=true、problems=[]。
最终reading-required汇总因缺少Pillow运行依赖而失败，整轮仍为未通过。

`fa54027…`仅在汇总作业补齐python3-pil，预算、引擎、门禁断言未改；
完整17作业重验run [39902467216](https://github.com/NoGod3524/EXReader/actions/runs/39902467216)已启动。
最终结论以这次同source/run/attempt的完整执行及严格汇总为准。

下列旧候选封装与协议记录只授予各自固定源码的声明范围；实际发布和默认分支规则仍未执行。

## 候选封装

复用`reading-core.yml`两个Linux preset的构建与安装，在同一个stage执行现有严格许可检查，
并通过独立安装消费者核对SDK运行库版本/ABI与头文件；library额外使用公共API创建书库，
读取该库的实际application_id/schema7。消费者不链接源码树内部目标。

`tools/reading_release.py`核对profile/许可/九格式smoke的同源码结果、全部安装消费、
安装文件与组成清单的逐文件身份，输出带完整source/run/attempt、实际版本与逐文件SHA-256的
tar.gz和清单。归档包含隐含文件；拒绝symlink、越界、已有输出和安装后变更。
相同输入、身份和源码时间生成相同归档。候选不创建tag或发布：`published=false`、`quality_accepted=false`。

六平台候选接线已在源码`df01224b6bd44cc2291d5b2ab9bc1efc022dfd43`、
[run 39893977984](https://github.com/NoGod3524/EXReader/actions/runs/39893977984) attempt 1通过：
protocol与六个构建作业7/7成功，封装正反例54/54。
Windows/macOS仍执行core25项、library30项平台拒绝回归；各包的许可材料与九格式smoke通过。
所有包实际SDK 3.40.0 / ABI 1；library为3.34.0 / schema 7，core不含书库。

| 平台/架构 | profile | tar.gz字节 | Actions工件ID | 工件ZIP SHA-256 |
| --- | --- | ---: | --- | --- |
| Linux/X64 | reading-core | 6,116,917 | 12475767427 | `4db990c7e6e431b9165055433c834f890a47191ea194e19ad2cf28806d01065c` |
| Linux/X64 | reading-library | 6,917,736 | 12476370335 | `78f9048a47a5ff7a059cd7189b1cb5d6d7c25715051e4b2bc8c4395de7b30c0c` |
| Windows/X64 | reading-core | 8,159,629 | 12476022357 | `d4b5df92312a15231e97d50506c5876e4598a8091a405d63052bb2224731b300` |
| Windows/X64 | reading-library | 9,364,378 | 12475624441 | `f299983b9f8d77d973f101c3861cdb993cd64471aace5dc4d8ae46411026151e` |
| macOS/ARM64 | reading-core | 5,392,472 | 12475907054 | `7d754cf0001189d8e4d1ef329a3c698463b7a759d8e4f98f0e2e7626ec474cfa` |
| macOS/ARM64 | reading-library | 6,182,973 | 12476116887 | `5498a53e3bcb74c52e70fefc95db83a4b4f525f7e9bbcdf28c0ddd8d87a397fe` |

上表字节为包内SDK归档，不是Actions ZIP大小或阅读程序体积；ZIP digest直接取自Actions API。
六工件均绑定同run/source，核对时非空、未过期。包内清单另有SDK归档与逐文件SHA-256。
总门禁将逐一重核六包；该封装运行不含后续NASA修复，也不授予质量验收或新SDK冻结。

`.github/workflows/reading-release-candidate.yml`先执行封装正反例，再复用实际构建。
合成自验fixture只验证判定代码，不能替代真实安装消费。

## 后续接线

默认分支总门禁已在候选分支接入原生正确性/sanitizer、阅读profiles、平台组成检查及R2/R3固定语料/预算。
R2/R3报告必须绑定同source/run/attempt及冻结清单/测量契约/预算身份；诊断或缺证据不能变成发布通过。
原生七个检查不由Linux profile替代。R4改变核心后由集成人重新验证并冻结SDK。

GitHub默认分支当前`codex/framework`、rulesets仍未启用；About已更新为原生多格式/自有PDF/无WebView和MIT核心、可选依赖分别许可的说明，并云端读回。
本包会先固定实际产生的check名及可审阅规则，再启用门禁并读取云端配置确认。
发布动作与候选封装分开；最终产物只能使用已接受源码、固定版本及同次工件，回退指向原有不可变版本，
不覆盖旧tag、工件或失败。当前尚未授予R6整体完成。

## 当前云端接线与冻结影响

候选封装源码`65c968d65eaf274367bd645fd479a983f5a538a4`的run `39887578472`
三个作业全部成功，封装协议32项通过；两个实际安装SDK分别封装235/238个文件。
纯文档后继`99a7b3d7967c0b0888de2d4106e33cbdd3069027`的run `39887835489`也成功。
它们仍是`quality_accepted=false`的候选，不是产品或发布验收。

总门禁源码`76eb39d768559692825b1ee2ac1bab16abc3d10d`的run `39890734935`
实际启动17个作业：protocol 1、原生7、Linux profiles 2、Windows/macOS profiles 4、R2 1、R3 1、最终汇总1。
协议作业已确认封装32项及总门禁元数据37项通过。R3因尚无冻结预算按设计失败；
真实文档仍有开放缺陷，因此本轮不得授予总门禁通过。

`reading-required`始终执行，即使上游失败、跳过或取消；严格汇总拒绝这些状态，
核对八份报告工件的同source/run/attempt、有效digest、非空和未过期，再检查封装、许可、
平台拒绝回归、R2完整声明，以及R3冻结预算和原始证据。下载和重新审计均只发生在云端。
报告保留`published=false`、`complete_product=false`及零WP16信用。

后继门禁进一步核对当前attempt精确17个作业及十份必需native工件；不接受部分重跑沿用的旧native成功。
`fdf93b8`的run `39892685541`三作业成功，封装32项、门禁55项协议通过。
PR合并提交与GitHub运行元数据的分支头分别绑定，避免混淆实际受测源码。
run `39892833007`只读观察真实`reading-required`检查，确认发布者为GitHub Actions、integration ID 15368；
预备规则已绑定该发布者，仍为disabled，尚未修改仓库规则。
许可/平台拒绝报告新增同run/attempt与原报告散列绑定，R2聚合重核逐项原始附件，R3预算重核固定基线ZIP内的原报告。
这些后继接口仍需在最终共同源码完整验收，不因协议自验单独授予发布通过。

为复用原生七作业，`native.yml`仅增加`workflow_call`入口，原步骤不变。
该文件属于保护树，因此新SDK冻结必须纳入这一变化及后续核心修复；不能继续转授旧K的结果。
当前默认分支尚未安装本工作流，分支规则也尚未启用。

六候选汇总与纯发布准备工具已合入集成源码`76c8750d8e66ee7b0ae2ccdbe4a277521b51b36a`。
[run 39895440589](https://github.com/NoGod3524/EXReader/actions/runs/39895440589)三个作业成功，
封装协议54项、总门禁协议92项、发布准备协议57项均通过，Linux两profile安装与封装通过。
总门禁新增逐一核六份candidate/manifest/归档/许可的来源、平台架构、版本和schema，
保留H6、PR合并源码、签发者及当前attempt原生作业检查。
发布准备还核对已接受摘要中的六包清单、远端默认分支祖先关系和既有版本，
原样导出该轮六包与SHA256SUMS；不创建tag或Release。
真实发布准备仍等待最终同源总门禁与默认分支接纳，协议通过不代表已生成可发布版本。
