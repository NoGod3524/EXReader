# 真书全量基线 · 2026-11-07

源码：main `c665d1cb1c0b681d4365f732acf775167bfa6d33`；SDK 3.42.0 / ABI 1。本地 Release 构建，4 路并行，无缺书、无失败。

- 覆盖：**19/19 本，11,128 页，8,694,817 字形计数**。
- 首轮墙钟：**146.653874 秒**；各书耗时合计：520.356691 秒。
- 第二轮墙钟：92.073813 秒；各书耗时合计：291.351171 秒。
- 两轮渲染墙钟合计：238.727687 秒；不含构建、负对照和报告整理。
- 幂等：两轮全部 11,128 页、尺寸和字形计数一致，0 页哈希变化。
- 内容指纹：`a92cd1a358726ead98d594d50ae59c7f2943969eef104410bf342cb184c21a0d`。
- 改书负对照：只修改《The House on Mango Street》的一个 EPUB 正文段落并重渲染整本，页数仍为 181；比较 CLI 退出码 1，只识别到该书第 7–13 页（0 起始）共 7 页像素变化。其余 18 本复用首轮结果。
- 负对照渲染：2.219388 秒；临时副本自动删除。
- 比较器自检：有效像素/padding、增删页、独立页数变化、增删书、缺书、条件不兼容均通过。

首轮最快：**between-the-world-and-me**，2.724256 秒 / 228 页。
首轮最慢：**the-autobiography-of-malcolm-x.**，77.779635 秒 / 279 页。

| 书籍 ID | 语言 | 页数 | 字形计数 | 首轮秒 |
| --- | --- | ---: | ---: | ---: |
| a-raisin-in-the-sun | en | 354 | 201205 | 9.725816 |
| between-the-world-and-me | en | 228 | 206269 | 2.724256 |
| black-boy | en | 1013 | 827318 | 25.068025 |
| born-a-crime | en | 501 | 463620 | 11.003640 |
| crying-in-h-mart | it-IT | 506 | 454828 | 18.697592 |
| how-does-it-feel-to-be-a-problem-being-young-and-arab-in-america | en | 492 | 591547 | 18.743399 |
| i-know-why-the-caged-bird-sings | en | 625 | 445291 | 35.587360 |
| pachinko | pt | 1214 | 932467 | 61.772993 |
| the-absolutely-true-diary-of-a-part-time-indian | en | 560 | 248896 | 19.947657 |
| the-autobiography-of-malcolm-x. | en | 279 | 1084554 | 77.779635 |
| the-distance-between-us-a-memoir | en | 702 | 575181 | 43.172449 |
| the-fire-next-time | en | 187 | 138733 | 23.378696 |
| the-fire-this-time-a-new-generation-speaks-about-race | en | 314 | 297533 | 16.319756 |
| the-house-on-mango-street | en | 181 | 105411 | 5.876139 |
| zami-a-new-spelling-of-my-name---a-biomythography | en | 625 | 580338 | 24.408012 |
| hongloumeng-24264 | zh | 1632 | 821108 | 57.816350 |
| xingshihengyan-24239 | zh | 1167 | 562814 | 47.379611 |
| tangshi300-52323 | zh | 86 | 50095 | 4.826528 |
| kusamakura-japanese-vertical-writing | ja | 462 | 107609 | 16.128777 |

PDF 字形计数为有文本映射的 glyph 区域数；可重排书为 layout glyph 数。每页耗时包含取页/栅格化/哈希（PDF 还包含文本区域计数）；整书耗时另含打开、建立 pager、清理和原件哈希校验。

文件：

- [baseline.json](baseline.json)：19 本全部逐页哈希、计数、耗时和运行身份。
- [baseline.diff.json](baseline.diff.json)：首次建基线的覆盖结果。
- [idempotence.diff.json](idempotence.diff.json)：第二轮逐书零差异报告。
- [verification.json](verification.json)：全量幂等和实际改书负对照。
- [build.json](build.json)：编译器、完整 EXR 选项、本地依赖源码指纹、DLL 哈希与 ctypes/native 结构尺寸校验。

语料来自任务指定位置，前 15 本原件 SHA-256 全部与既有 RESULTS.csv 匹配；第二轮完整 JSON 保留在仓库外 `C:/Users/Oscar/Documents/Codex/w2-realbooks-build-20261107/repeat.json`。只提交哈希与计数等元数据，无原书、正文或图片。

重跑和 PR 验证步骤见 [docs/REGRESSION.md](../../docs/REGRESSION.md)。本轮未手动启动 CI，未修改或取消 workflow。
