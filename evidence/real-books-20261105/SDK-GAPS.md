# SDK 缺口登记 · 2026-11-05

## SDK-LAYOUT-001 — 缺少最大行宽配置

**layout 配置缺少 max_measure（最大行宽）参数，宿主必须自行施加。**

- 触发条件：直接使用 SDK CLI 渲染，视口 1280×800、字号 18 px；当前示例设置 margin=36，未另行限制正文列宽。
- 视觉评审观察：拉丁文字行过宽，长行约 110+ 字符。Pachinko 本地版本为葡萄牙语，不能将该观察标为英文行长统计。
- API 现状：`include/exr/layout.h` 的 `exr_layout_options` 提供 width/height/margin/font_size/line_height/paragraph_spacing，没有独立的 max_measure 配置。CSS 已有 max-width 等能力，这不等于 layout 配置已有独立、默认生效的阅读行宽约束。
- 接入影响：第三方如果直接按整个视口排版，需要自行限制正文列宽；宿主外壳的 28–34em 行宽范围属于宿主施加的限制，字号 18 px 时约为 504–612 px，不能据此宣称 SDK 已提供该配置。
- 分类：SDK 接入/阅读舒适度缺口；未阻止解析或渲染。只登记，本轮未实现 max_measure，也未改算法、默认值或公共 API。
- 视觉复核及后续第 3 步验收项见 [VISUAL-REVIEW.md](VISUAL-REVIEW.md)。
