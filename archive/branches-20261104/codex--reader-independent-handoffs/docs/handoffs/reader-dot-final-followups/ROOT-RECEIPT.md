# D08–D14 主协调者接收记录

2026-10-25，用户确认交接汇总已封存；root已用只读Git取得下列六个远端文档HEAD。
交付封存不等于产品通过，所有原失败与限定范围继续保留。

| 包 | 远端封存 HEAD | 审查入口与结论 |
| --- | --- | --- |
| D08 | 30158c44dcd9ebf27e028b85f60c4fe374b9c90b | Windows焦点/边界/像素审查；整体false。原生高DPI150/200未达成、对比度pending；隐藏阅读页接收焦点和初始工作区溢出为实际问题。 |
| D09 | 8f55aa391cf14472dbe4025b3fa2acba20d4cac9 | GTK四会话各19/20；快捷键打开records时焦点在modal外，整体false。原D03撤回通过与D09失败保留。 |
| D10 | 7e4fcac25120199dd4818a86039e2257f28132a1 | Mac6/6、iPad10/10、iPhone8/10。两个大字体新驱动场景失败；不推断产品失败，不授全Apple或六平台。 |
| D11 | da3ba2d1544edff6dc5004dd9d9d88aa732f9b12 | 六目标均执行，整体false；Android catalog observer和macOS picker前置条件尚未闭合，不跨轮拼接。 |
| D12 | df78d4f5248deb7c1ac04b6cf7376a8fe0f80b6b | 最终harness初始化失败；只按第二轮真实GUI观察保留高亮选区缺失、真实NULL的Open/Edit启用问题及固定页窄通过，不继承最终轮未执行的Edit。 |
| D13 | 未取得已核验提交或执行分支 | 用户更正：执行在实验前被检查终止，但完整拒绝原文、具体命令及规则无法找回；“网络安全风险”只是概括。无已核验运行或工件，未验收。不能断言某项路径操作被明确禁止，也不得改写实验或换入口重试。仅另做只读源码审查，见D13-SOURCE-REVIEW.md。 |
| D14 | 93c2f583c7e54eb2aebcba13a18b532bd0a967f5 | Windows有界24周期/244检查通过；GTK仅第一阶段，未观察到live interval，cleanup后被harness终止，整体false。 |

各包原始 `HANDOFF-RESULT-Dxx.md`、文档验证记录和云端原ZIP为详细证据入口。
root本地没有下载或处理原工件，后续需要的重新认证仍只在Actions。

## 已开始的产品修复

独立候选 `codex/reader-native-owner-repairs` 从共同源码96270a2b建立，
root初始源码479b60ae由子代理继续审查和云端验证；尚不进入当前共同候选或默认分支。
包括Windows共享可见/可操作焦点恢复、真实FOUND后的选择发布、NULL位置操作禁用、
初始工作区边界，以及GTK共享records入口的modal初始焦点。
RAW NULL 的 `has_location` 单独不足以认定可跳转，须保留真实指针/内容可用性语义。

新owner guard将明确登记实际修改与原业务测试身份，不声称旧unchanged-owner门禁执行通过。
真实frame范围、EPUB part、固定页与selection必须只读观察；成功文案不替代位置验证。
其余D10/D11/D14驱动缺口独立安排，原预算和原失败均不改。
