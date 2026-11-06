# SDK 缺口登记 · 2026-11-05

## SDK-LAYOUT-001 — 缺少最大行宽配置

**layout 配置缺少 max_measure（最大行宽）参数，宿主必须自行施加。**

- 触发条件：直接使用 SDK CLI 渲染，视口 1280×800、字号 18 px；当前示例设置 margin=36，未另行限制正文列宽。
- 视觉评审观察：拉丁文字行过宽，长行约 110+ 字符。Pachinko 本地版本为葡萄牙语，不能将该观察标为英文行长统计。
- API 现状：`include/exr/layout.h` 的 `exr_layout_options` 提供 width/height/margin/font_size/line_height/paragraph_spacing，没有独立的 max_measure 配置。CSS 已有 max-width 等能力，这不等于 layout 配置已有独立、默认生效的阅读行宽约束。
- 接入影响：第三方如果直接按整个视口排版，需要自行限制正文列宽；宿主外壳的 28–34em 行宽范围属于宿主施加的限制，字号 18 px 时约为 504–612 px，不能据此宣称 SDK 已提供该配置。
- 分类：SDK 接入/阅读舒适度缺口；未阻止解析或渲染。**当前实施归属为宿主第3步**施加正文行宽限制；SDK缺少独立参数这个事实继续留档，不在本轮扩展公共API。
- CJK证据范围：28–34字的样本口径目前只有日文草枕对照，15本原语料无中文；中文行宽待补书后独立验证，不能按日文结果结案。
- 责任分流及后续独立验收项见 [VISUAL-REVIEW.md](VISUAL-REVIEW.md) / [CJK-READABILITY-CHECKLIST.md](CJK-READABILITY-CHECKLIST.md)。

## SDK-TEXT-002 — hyphenation 后续版本验收

- 归属：**引擎能力，后续引擎版本，不在2a范围**。本轮只登记。
- 事实：SDK已有 hyphenator 与 `exr_pager_set_hyphenator` API；本轮视觉CLI未加载断词字典或设置hyphenator，图片没有断词不能用来证明SDK完全缺少该能力。
- 未完成范围：所需语言字典/模式、断词策略及实际效果的后续引擎验收；不得随宿主第3步/第5步的样式验收一并宣告完成。
- 首行缩进独立结案：Pachinko第257页[像素判定A](TEXT-INDENT-PIXELS.md)，作者显式1.2em已应用，不登记为引擎缺陷。作者未指定时的CJK缺省策略仍归第5步，见 [TEXT-INDENT.md](TEXT-INDENT.md)。

## SDK-CJK-003 — 连续标点未观察到挤压

- 草枕原包462页的字形坐标中，74组连续标点的两字总占位/单字advance均为2.000，平均每标点1.000；横排坐标控制的同一74组结果一致。
- 代表组合：第57页`。「`，两个advance均19px，合计38px，参照单字19px。未达到本轮“小于一字”的压缩判据。
- 归属：引擎CJK排版能力，后续版本；只记录、不修复，不归宿主默认缩进或宿主行宽。
- 详情与轴向口径见 [CJK-LINEBREAK.md](CJK-LINEBREAK.md)，统计数据见 [CJK-PUNCTUATION.csv](CJK-PUNCTUATION.csv)。指定避头尾字符集违规为0，禁则与标点挤压分别结论。
