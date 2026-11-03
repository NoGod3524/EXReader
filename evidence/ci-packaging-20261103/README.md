# P acceptance evidence

基线：342780237eb013350bff20c21bc92c335422526a（V 合并结果）。

范围：Apple 产品安装、构建 fail-fast、空值诊断、预期失败错误保留、逐行自衰减 CI 基线。CI-DEPS-001 为打包遗漏，归 P；不修改 SDK 身份、产品断言、F07、catalog 或 ledger 工作流。

local.txt 保存本地正例与运行/基线负例；cloud.json 登记后续必要 job 的 run/source/result，不用预期结果代替实际返回。R 候选必须在 P 与 provider 变更之后重新选取。
