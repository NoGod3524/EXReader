# 格式组合候选交回

完成：`codex/reader-format-combination` 的受测源码 `8015c576822d5284dedfea17428ecf1a240befd0`，完整第 2 轮 [40244430230/1](https://github.com/NoGod3524/EXReader/actions/runs/40244430230) success。第 3 轮未启动。

Windows/Linux 同一源码、同 attempt 均为 baseline/candidate 各169项原 native、RTF100、CBZ103通过；F5 v2各18/18。strict job `121326920910` 实际认证本轮四份原 ZIP、程序/DSO与原始结果后重算通过。原 v1 失败和完整第 1 轮缺 DLL 失败均保留。

- [完整结果及作业/工件/树身份](docs/reader-format-combination/RESULTS.md)
- [严格汇总原值、历史轮诊断、Windows DLL 正反验证](docs/reader-format-combination/acceptance.json)
- [方案及固定来源](docs/reader-format-combination/PLAN.md)

候选 SDK whole tree `dd5f4fa912bcaab483524a76988515c731f22702`，src tree `001bd8d0baa49ecde6fae82d799bafd0b007030f`。只在隔离副本应用固定 RTF/CBZ 两补丁；SDK 3.41.0 / ABI 1 未变。

`candidate_package_accepted=true`、`f5_v2_accepted=true`；`sdk_adopted=false`、`host_integration_accepted=false`、`complete_product=false`，1710仍0/1710。等待 root 审查；未发布或接入主线。
