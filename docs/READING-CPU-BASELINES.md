# R3：按实际环境冻结独立基线

2026-10-23，用户选择为云端出现的新CPU型号分别建立独立基线，保留原预算。
SDK仍为`9854061be331fe603a1822d9b2b36ee357154927`。

## 原预算

`tests/reading_real/budgets.json`与原逐页审阅记录、测量契约保持逐字节不变。
原预算SHA-256为`75142b54f03b62d8f12752ff96fbc2f8e7f0d910511ec218165c39844ef5b0f3`，
仍只授予原AMD EPYC7763环境。新CPU不使用旧CPU的耗时阈值。

此前Android PR的39991113462、39992864599和Apple PR的39998455203
均在采样前拒绝环境，保留失败，不授予测量或预算通过。

## 独立采样与冻结

`reading-real.yml`的`baseline_only`仅供显式dispatch使用，不能与
`require_budgets=true`组合；必过工作流不能选择此模式。每个run仍执行八份原件、
40个新进程及12次参考页渲染。有效测量报告为`measurement_valid=true, accepted=false`。

固定来源`9442e84d60469de5551de7ce7e62191a0059d9d1`的独立采样：

| CPU | run | 用途 |
| --- | --- | --- |
| AMD EPYC7763 | [40010385179](https://github.com/NoGod3524/EXReader/actions/runs/40010385179) | 原环境复测，不替换旧预算 |
| AMD EPYC9V45 | [40010390609](https://github.com/NoGod3524/EXReader/actions/runs/40010390609) | 独立新环境基线 |
| Intel Xeon8573C | [40010395155](https://github.com/NoGod3524/EXReader/actions/runs/40010395155) | 独立新环境基线 |

三轮均完整有效。此前39994248838的多job候选继续保留为诊断数据；
上述正式种子使用原有单job工作流，保持旧的工作流、作业、原件和祖先关系守卫。

导出器在云端重核每份原ZIP、40份原生输出、12份参考输出和图像，沿原契约公式生成预算。
只有全部12对图像字节及全路由签名与原已审阅记录完全一致，才可继承其逐页finding，
并登记等价来源；差异必须另行审阅。导出不执行新测量，也不授予严格预算通过。

预算先提交，再以另一轮同源、同环境完整运行验证。各CPU的样本、基线、阈值和结果独立，
不合并分位数或时长；WP16进程CPU记账保持不变。

## 精确选择与汇总

`tests/reading_real/environments.json`登记CPU、编译器、参考工具、系统、架构及runner image。
选择器要求这些字段逐项相同，并核预算路径及内容SHA；未知环境、重复登记、缺文件或
篡改散列均拒绝，不使用近似型号或默认新预算。原7763预算必须始终保留一次登记。

每份报告绑定`budget_path`、`budget_sha256`、环境ID及注册文件SHA。
必过汇总重新选择环境并重审原始测量，拒绝报告改指另一份预算。
基线来源仍必须是早于候选的祖先，且原run、attempt、作业及未过期工件均有效。

选择器拒绝回归在[40011312358](https://github.com/NoGod3524/EXReader/actions/runs/40011312358)
通过39项；同轮独立采样完整有效，仍为`accepted=false`。
新环境严格验收在预算落源后单独登记。
