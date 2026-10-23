# R6：阅读SDK门禁与发布接线

起点`9bd2b2c3caf1f63dc4437e0af978247494e87145`；既有SDK冻结与四宿主结果保留在
[冻结记录](R5-SDK-FREEZE.md)。本包不改变SDK实现或公开API。

## 候选封装

复用`reading-core.yml`两个Linux preset的构建与安装，在同一个stage执行现有严格许可检查，
并通过独立安装消费者核对SDK运行库版本/ABI与头文件；library额外使用公共API创建书库，
读取该库的实际application_id/schema7。消费者不链接源码树内部目标。

`tools/reading_release.py`核对profile/许可/九格式smoke的同源码结果、全部安装消费、
安装文件与组成清单的逐文件身份，输出带完整source/run/attempt、实际版本与逐文件SHA-256的
tar.gz和清单。归档包含隐含文件；拒绝symlink、越界、已有输出和安装后变更。
相同输入、身份和源码时间生成相同归档。候选不创建tag或发布：`published=false`、`quality_accepted=false`。

`.github/workflows/reading-release-candidate.yml`先执行封装正反例，再复用实际构建。
合成自验fixture只验证判定代码，不能替代真实安装消费。

## 后续接线

默认分支总门禁需同时接入原生正确性/sanitizer、阅读profiles、平台组成检查及R2/R3固定语料/预算。
R2/R3报告必须绑定同source/run/attempt及冻结清单/测量契约/预算身份；诊断或缺证据不能变成发布通过。
原生七个检查不由Linux profile替代。R4改变核心后由集成人重新验证并冻结SDK。

GitHub默认分支当前`codex/framework`、rulesets为空；About仍为旧GPLv3说明，仓库LICENSE为MIT。
本包会先固定实际产生的check名及可审阅规则，再启用门禁并读取云端配置确认。
发布动作与候选封装分开；最终产物只能使用已接受源码、固定版本及同次工件，回退指向原有不可变版本，
不覆盖旧tag、工件或失败。当前尚未授予R6整体完成。
