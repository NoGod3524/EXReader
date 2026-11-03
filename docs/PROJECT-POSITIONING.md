# EXReader SDK 定位
EXReader 是 C11 引擎与 SDK，**不在本仓库推进六端阅读器产品**。六端阅读器是独立项目，目标仓库与接收人待指定。

交付物：C11 引擎、公共头文件、可迁移 CMake 包、六包产物、许可证清单、基准报告。使用者是将阅读能力嵌入自己应用的开发者。
支持子集与限制追溯 docs/SUPPORT_MATRIX.md、docs/NATIVE_API.md 和 docs/SDK_COMPATIBILITY.md；其中历史版本文字不是当前总 SDK 3.42.0 的验收证据。

- 受支持示例：Windows + GTK。
- Android / macOS / iPhone / iPad：build-only，只保证编译，不做产品验收，不设四个平台的独立计分项。六包清单不等于六端产品通过。
- 不承诺冻结子集之外的格式/CSS/PDF特性、真机或完整应用生命周期。
- 产品顺序按 owner 决策保持 3 → 1 → 2。V 固定总 SDK 3.42.0、组件独立版本；3.42 历史交付证据尚未完成复验，未来 refreeze 候选为 3.43、ABI epoch 1；C 只新增治理文档；R 候选必须在 V 之后，且 refreeze 仍需 owner 明确“执行”。本文件不声称 V 或 R 已完成。

v1 108项冻结只读，不改 state；实际改名 catalog-v1.json 与 archived 标记仍待单独执行。v2 另开84项：引擎40 / SDK契约与交付20 / 示例宿主12 / 证据与语料12，全部初始 pending，不继承旧分数。
详见 [catalog-v2.json](reader-total-progress/catalog-v2.json) 和 [移交清单](deferred-reader-gates.md)。

C 落点：codex/governance-to-ledger-20261103，基于 ledger/base-20261103 @ 342780237eb013350bff20c21bc92c335422526a，只新增文件。draft PR 不授权合并；默认分支、Settings、ruleset 不变。

版本身份见 [VERSION-LINES](https://github.com/NoGod3524/EXReader/blob/342780237eb013350bff20c21bc92c335422526a/docs/VERSION-LINES.md)：历史F06与本次V均称3.42.0，但同号不同源；版本号不能替代源码提交与工件身份。V已合入ledger/base；R仍未执行。
