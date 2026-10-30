# 当前失败修复进度（不是最终handoff）

2026-10-29 21:32 美东。用户最新真实请求“修复这个大概要多久，你全力去修复他们”，root已继续处理当前已确认的GTK和Apple mobile失败；原6个worker保持停止，未重启或新建。最终handoff、共同分支合入、同源码完整回归都尚未交付。

## 已通过的定向范围
- GTK source c1de24844830e5f389c37a4cfe744ed60e2d0b51 / producer40980931719：32主启动520样本，12交互启动240样本；原verifier通过。
- 原ZIP独立40983431462 / source e983dfb2a7cd5b441cd70a85c463faa4d0a7f4fa / job123828707206；artifact12946026796 /728B / SHA256d6444e6f0cc9ea6365e8a7686c7eecdf3569fcaf1c00f7bd3f1148876631160c。
- 组织开关 source a6e2e506f70a86afc56fe7da5db9fa8186caf1f8 /40981500259：iPhone、iPad各原6通过。新原生Toggle的真实开关命中范围被正确标记；原macOS分支保留。
- 上述不是共同源码的完整通过，不授F08数值预算或F12完整交付。

## Apple原5定向首轮失败与后续修复
source550556de68ba1d861cc3fcce8f4a60a66706f7c2 /40982450461：iPad4/5（批注timeout），iPhone3/5（批注timeout，share返回断言失败）。
- iPad原ZIP12945688879 /186995142B /5277167b985c1063abd4ab907cf850ad5ea7ea660bdfcec1184ff94cd432e67c。
- iPhone原ZIP12945943862 /203429036B /a123ebd1a4748e07e6683aad7efc5839a398442e942ca4072e3cbf76dc45e2aa。
- Actions原ZIP诊断40984758032、40984894051、40985221514：慢拖反复穿越多个区域；无效文件选择后generic features.cancel缺失查询触发远程Files进程kAXErrorInvalidUIElement，61.07秒后重试。
- iPhone原ZIP诊断40985582904、40985784107：adapter的features.share.native标记消失但ActivityListView仍开着；原body因此跳过native.exists条件下的关闭滑动，最终features.close被遮挡。原始“先关掉分享再操作详情”断言必须满足。
- 新helper远处原生fast flick、近处受控slow drag；真实可见交集>=12px且enabled/native hittable才坐标点击。强类型查询button/text/scroll，选择文件后必须真的返回可点击的features.close。分享marker映射到观察到的真实ActivityListView，不以旧marker消失当关闭成功。
- 新产品补丁保留UIActivity completion callback清空SwiftUI sharing绑定。原5正文、setup/teardown、90秒wait、24次拖动上限、原240/360预算均保留。
- source21194f4cf54cdd422ebd2472b437fa8616ebff6a /40985138048为仅快速滑动的早期候选；source04f8cbf0e092c31efa51e1c7d798346db125b76e /40985492438增加typed+picker返回，但仍未修分享真实容器；两者已发取消请求作为superseded保留，不能称产品通过。
- 当前source908c07ef41ddca602d7147f807af9511174db5e0 /40986067818包含上述已解释修复，等待实际原5 iPhone/iPad结果。

## 共同源码与独立审计准备
- remote共同codex/public-product-resume-20261029仍343bb94eb6513beaf5b344e7828342f6602a3b7b，无新合入。
- VM共同worktree HEAD9330be495bffdf3bf421bdc32b963e3fbfc4c9fe，仍有未commit的组合准备；79精确producer/doc blob +10 composition文件=89路径。当前暂绑定04f8版本，须等新候选实际通过后更新到正确source/helper blob再提交。
- 不得转授9330、fd592、各独立旧source通过给新组合。新组合必须跑C1/C3/270/Windows67+10/record27+8/C2/Apple原39x3+12supp全部同源码CI、原ZIP独立核验，然后共同分支只fastforward到同一个已测SHA。
- 审计分支758b63b1新9文件已提交：closure_*_independent.py八脚本与workflow。40986172637只做Actions语法检查通过，不执行验收。final orchestrator SOURCE=PENDING_REPAIR_SOURCE、7个run=0，必须用实际最终source和runIDs填实。
- 完整独立workflow暂存VM /tmp/exreader-final-audit-full.yml，实际审计前复制回workflow；当前预备workflow明确只有syntax job。
- Apple独立稿重算19个原ZIP、2SDK文件树、3平台原39、5程序身份、12supp文件/程序/原结果；C2独立稿重算6ZIP与GTK完整计划/实际native scroll traces。尚未执行这些新共同source审计，不得提前授通过。

所有构建、语法、测试、工件下载解析只在Actions。默认分支/PR/tag/Release未动。旧dirty未覆盖。95/108仍是最近真实目录审计口径，本轮尚未做新目录审计。
