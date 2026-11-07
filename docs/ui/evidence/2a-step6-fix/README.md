# Step 6 真书复核证据

PR #67 暂不可验收：owner 报告的裁切尚未复现。本次是诊断与真书验收补充，未改变图片绘制行为。

- [探针、flags 语义、六项数字与未决问题](../../2A-STEP6-FIX.md)
- [紅樓夢原件封面：深色 1242×742](cover-dark-1242x742.png)
- [Pachinko 原件正文：深色 1242×742](body-dark-1242x742.png)
- [真书 15 组封面、4 本正文、焦点结果及验收状态](result.json)
- [179a429a 与诊断构建三尺寸完整截图对照：0px 差异](record/179a429a-real-cover-comparison.json)
- [原件、EXE、运行库和源码哈希](record/real-metadata.json)
- [离屏 GUI 进程记录](record/real-processes.json)
- [既有 8 项](record/step5-result.json)、[字号锚点 12/12](record/font-anchors.json)、[P0](record/p0-result.json)、[三个无窗口检查](record/native-checks.json)
- [本轮原始 PNG、测量 JSON、drive、日志、paint trace](record/real-measurements.tar.gz)

新脚本 `check_step6_real.py` 固定原件 SHA-256，不生成或重写 EPUB；压缩包不包含书籍原件和书库数据库。焦点截图采用离屏 owner-draw 状态注入。

`record/metadata.json`、`record/processes.json`、`record/measurements.tar.gz`、`record/historical-*` 保留自 179a429a，属于上一轮记录。本轮记录使用 real- 前缀；result.json 与四张顶层截图已由本轮真书结果更新。
