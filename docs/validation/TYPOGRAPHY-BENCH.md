# 字体与排版性能基准 · 2026-11-07

18 组 × 3 个独立进程，共 54 次、1,080 次翻页。每格取三次中位数；完整单次数据在 [runs.csv](../../evidence/typography-bench-20261107/runs.csv)，逐次原始 paint.csv 和截图在同目录 raw/。

## 三个数字结论

1. **字体**：1552×928、行高 1.75，衬线 p95 171.97 ms，无衬线 188.11 ms，差 -16.13 ms（-8.58%）。三次范围分别为 63.95 / 14.05 ms；差值未同时超过两组各自的离散范围。
2. **行高**：1552×928 衬线，1.60→1.75→1.90 的 p95 为 186.14→171.97→190.21 ms，页数为 954→1038→1117。
3. **文件与首屏**：衬线 23.97 MiB，无衬线 15.68 MiB；1552×928、1.75 的字体加载分别为 30.26 / 25.31 ms，首屏渲染分别为 18.05 / 28.93 ms。

## 固定条件与口径

- 同一本《紅樓夢》、同一 DLL `892ea1acb0a519748d9b51c2f5f946d762b7f78d1015d42f811db3ba8fd18865`、同一宿主 EXE `51c868f7555a9a9109864163433aaf08a6dc32bc1b847a1137b07e05f24f64f2`。
- 字号 18 px，注入排版 DPI 96；两种客户区分别精确为 1242×711、1552×928。正文宽均为 612 px，高分别为 551、768 px。系统实际窗口 DPI 为 120，含边框整窗实测 1260×758、1570×975，与任务给出的整窗 1242×742、1552×955 不同；矩阵严格固定的是所要求的客户区。
- 每次从干净书库副本启动，字体在启动时加载，导入不计入打开。字体/书/EXE/DLL/构建命令和哈希在 protocol.json；字体文件不入库。OS 文件缓存未清空，属于暖缓存、独立进程测量。
- 排版注入 96 DPI 后 18 px 不随系统缩放增大。沿用宿主整数像素舍入，正文行距 1.60/1.75/1.90 对应 29/32/34 px；标题等仍服从原书 CSS。
- 打开含字体 = font_load_ms + book_open_begin 到首个非零 present_gen。另存不含字体的 book_open_to_present_ms 和完整进程启动到首屏 startup_to_first_present_ms。首屏渲染 = 第一个 render_ms。该书首屏为封面，不能将首屏差异全部归因于字形或文件大小。
- 翻页 = paint.csv 中 input_gen 到下一个不同 generation 的 present_gen；在下一输入前配对，20 次 PageDown。p50/p95 用 nearest-rank（第 10/19 个有序样本）。保留原有追踪事件；另列栅格化 p95，避免混淆端到端延迟与 SDK 渲染成本。
- 内存为 Windows 进程 PeakWorkingSetSize / PeakPagefileUsage（MiB），在第 20 次翻页后、全书页数遍历前采集；每次独立遍历全书，页数必须三次一致。
- present_gen 位于 GdiFlush 后，表示 GDI 提交完成，不包含显示器扫描或 DWM 可见帧确认。顺序翻页保留宿主预取缓存；turn_raster_p95_ms 统计翻页区间内所有 render_ms，包含预取绘制。
- 按种子 20261107+轮次打乱顺序，三轮串行。离散度 = (最大值−最小值)/中位数×100%，不是置信区间。
- 测量前预设：端到端翻页 p95 >100 ms 为未达目标，>200 ms 为严重慢档。这是本轮响应目标，不是 FPS；不将 1000/p95 冒充帧率。
- 由现有 examples/reader.c 生成仓库外宿主副本，仅注入可变行高、字体计时和数页命令；产品源码未改。所有窗口 --offscreen，位置 (-32000,-32000)，使用既有 ops\capture_window.py 截图。

## 18 组中位数

### 1242×711

| 字体 | 行高 | 打开含字体 ms | 首屏渲染 ms | 翻页 p50 ms | 翻页 p95 ms | 栅格 p95 ms | 峰值工作集 MiB | 页数 | p95 离散度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Noto Serif SC | 1.60 | 812.69 | 9.02 | 156.11 | 211.79 | 16.79 | 178.57 | 1309 | 15.98% ⚑ |
| Noto Serif SC | 1.75 | 527.50 | 10.83 | 158.95 | 187.63 | 16.79 | 175.32 | 1458 | 52.34% ⚑ |
| Noto Serif SC | 1.90 | 552.03 | 12.62 | 159.31 | 183.73 | 22.71 | 175.39 | 1547 | 424.87% ⚑ |
| Noto Sans CJK SC | 1.60 | 489.43 | 9.07 | 156.38 | 186.74 | 8.86 | 168.10 | 1281 | 41.95% ⚑ |
| Noto Sans CJK SC | 1.75 | 483.65 | 10.46 | 156.07 | 238.84 | 8.10 | 171.25 | 1427 | 22.36% ⚑ |
| Noto Sans CJK SC | 1.90 | 444.04 | 8.66 | 156.14 | 182.07 | 7.88 | 170.16 | 1519 | 49.55% ⚑ |
| 宋体 | 1.60 | 495.06 | 10.46 | 157.05 | 208.90 | 7.35 | 172.20 | 1282 | 45.14% ⚑ |
| 宋体 | 1.75 | 468.13 | 8.24 | 155.61 | 220.64 | 6.76 | 171.96 | 1427 | 29.07% ⚑ |
| 宋体 | 1.90 | 676.04 | 9.38 | 147.71 | 172.64 | 7.04 | 172.11 | 1520 | 41.32% ⚑ |

### 1552×928

| 字体 | 行高 | 打开含字体 ms | 首屏渲染 ms | 翻页 p50 ms | 翻页 p95 ms | 栅格 p95 ms | 峰值工作集 MiB | 页数 | p95 离散度 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Noto Serif SC | 1.60 | 642.28 | 21.16 | 156.39 | 186.14 | 31.95 | 180.24 | 954 | 6.56% |
| Noto Serif SC | 1.75 | 486.03 | 18.05 | 156.61 | 171.97 | 20.50 | 183.12 | 1038 | 37.18% ⚑ |
| Noto Serif SC | 1.90 | 576.19 | 24.47 | 158.95 | 190.21 | 35.59 | 180.31 | 1117 | 11.51% ⚑ |
| Noto Sans CJK SC | 1.60 | 538.39 | 16.15 | 156.27 | 202.84 | 17.92 | 176.13 | 939 | 16.53% ⚑ |
| Noto Sans CJK SC | 1.75 | 627.82 | 28.93 | 171.95 | 188.11 | 20.65 | 175.98 | 1018 | 7.47% |
| Noto Sans CJK SC | 1.90 | 484.43 | 21.37 | 155.62 | 158.86 | 10.79 | 175.82 | 1097 | 39.00% ⚑ |
| 宋体 | 1.60 | 534.76 | 22.60 | 156.12 | 172.45 | 9.76 | 175.71 | 939 | 303.84% ⚑ |
| 宋体 | 1.75 | 741.58 | 26.23 | 158.98 | 175.32 | 14.78 | 173.81 | 1018 | 31.33% ⚑ |
| 宋体 | 1.90 | 741.19 | 25.73 | 158.09 | 173.20 | 13.39 | 176.90 | 1095 | 509.72% ⚑ |

## 衬线与无衬线

| 客户区宽 | 行高 | 衬线 p95 ms | 无衬线 p95 ms | 差值 ms / % | 两组范围 ms | 差值超过两组离散范围 |
| --- | --- | --- | --- | --- | --- | --- |
| 1242 | 1.6 | 211.79 | 186.74 | 25.05 / 13.41% | 33.84 / 78.34 | 否 |
| 1552 | 1.6 | 186.14 | 202.84 | -16.70 / -8.23% | 12.21 / 33.52 | 否 |
| 1242 | 1.75 | 187.63 | 238.84 | -51.21 / -21.44% | 98.20 / 53.40 | 否 |
| 1552 | 1.75 | 171.97 | 188.11 | -16.13 / -8.58% | 63.95 / 14.05 | 否 |
| 1242 | 1.9 | 183.73 | 182.07 | 1.66 / 0.91% | 780.62 / 90.21 | 否 |
| 1552 | 1.9 | 190.21 | 158.86 | 31.35 / 19.73% | 21.90 / 61.96 | 否 |

判定口径：绝对差值大于两组各自的最大值−最小值。逐组原值和比较在 font-comparisons.csv。

## 行高对 p95 和页数的影响

| 客户区宽 | 字体 | p95 ms：1.60 → 1.75 → 1.90 | 页数：1.60 → 1.75 → 1.90 | 页数 1.60→1.90 |
| --- | --- | --- | --- | --- |
| 1242 | Noto Serif SC | 211.79 → 187.63 → 183.73 | 1309 → 1458 → 1547 | 18.18% |
| 1242 | Noto Sans CJK SC | 186.74 → 238.84 → 182.07 | 1281 → 1427 → 1519 | 18.58% |
| 1242 | 宋体 | 208.90 → 220.64 → 172.64 | 1282 → 1427 → 1520 | 18.56% |
| 1552 | Noto Serif SC | 186.14 → 171.97 → 190.21 | 954 → 1038 → 1117 | 17.09% |
| 1552 | Noto Sans CJK SC | 202.84 → 188.11 → 158.86 | 939 → 1018 → 1097 | 16.83% |
| 1552 | 宋体 | 172.45 → 175.32 → 173.20 | 939 → 1018 → 1095 | 16.61% |

## 字体文件大小与首屏

| 字体 | 字节数 | MiB |
| --- | --- | --- |
| Noto Serif SC | 25129160 | 23.97 |
| Noto Sans CJK SC | 16437364 | 15.68 |
| 宋体 | 18316748 | 17.47 |

| 客户区宽 | 行高 | 衬线加载 ms | 无衬线加载 ms | 首屏渲染差 ms | 含字体打开差 ms |
| --- | --- | --- | --- | --- | --- |
| 1242 | 1.6 | 25.52 | 18.27 | -0.05 | 323.26 |
| 1552 | 1.6 | 32.36 | 17.46 | 5.01 | 103.89 |
| 1242 | 1.75 | 28.14 | 16.34 | 0.37 | 43.85 |
| 1552 | 1.75 | 30.26 | 25.31 | -10.88 | -141.80 |
| 1242 | 1.9 | 32.78 | 18.01 | 3.96 | 107.99 |
| 1552 | 1.9 | 26.07 | 15.67 | 3.10 | 91.76 |

正差值表示衬线更慢。字体文件相差 8.29 MiB；本实验同时改变格式、字形和字体内容，不能分离“每 MB 的加载成本”。

## 离散度及原因

翻页 p95 超过 10% 的配置 16/18。全部指标、三次原值、CPU 忙碌度及 >10% 标记在 dispersion.csv；页数离散度均为 0%。

| 配置 | p95 三次 ms | p95 离散度 | 其余 >10% 指标 | 系统 CPU 忙碌度范围 |
| --- | --- | --- | --- | --- |
| sans / 1.60 / 1242 | 237.66 / 186.74 / 159.32 | 41.95% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 44.53–62.77% |
| sans / 1.60 / 1552 | 189.88 / 223.41 / 202.84 | 16.53% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 57.72–83.27% |
| sans / 1.75 / 1242 | 241.53 / 238.84 / 188.12 | 22.36% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 43.38–60.54% |
| sans / 1.75 / 1552 | 189.38 / 175.33 / 188.11 | 7.47% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 88.56–96.46% |
| sans / 1.90 / 1242 | 175.43 / 182.07 / 265.64 | 49.55% | open_including_font_ms, turn_raster_p95_ms | 40.76–54.19% |
| sans / 1.90 / 1552 | 220.07 / 158.12 / 158.86 | 39.00% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 53.73–65.49% |
| serif / 1.60 / 1242 | 211.79 / 219.09 / 185.25 | 15.98% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 39.45–93.80% |
| serif / 1.60 / 1552 | 186.91 / 174.70 / 186.14 | 6.56% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 45.98–86.52% |
| serif / 1.75 / 1242 | 272.12 / 173.92 / 187.63 | 52.34% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 50.33–89.30% |
| serif / 1.75 / 1552 | 235.78 / 171.97 / 171.84 | 37.18% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 39.81–97.70% |
| serif / 1.90 / 1242 | 954.98 / 174.36 / 183.73 | 424.87% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 69.75–94.58% |
| serif / 1.90 / 1552 | 197.58 / 190.21 / 175.68 | 11.51% | open_including_font_ms, font_load_ms, first_screen_render_ms | 63.14–92.63% |
| simsun / 1.60 / 1242 | 208.90 / 252.48 / 158.17 | 45.14% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 42.73–63.52% |
| simsun / 1.60 / 1552 | 682.99 / 159.02 / 172.45 | 303.84% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 38.70–99.98% |
| simsun / 1.75 / 1242 | 171.84 / 220.64 / 235.98 | 29.07% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 41.97–43.67% |
| simsun / 1.75 / 1552 | 214.60 / 175.32 / 159.66 | 31.33% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 70.93–95.01% |
| simsun / 1.90 / 1242 | 232.54 / 172.64 / 161.22 | 41.32% | open_including_font_ms, font_load_ms, first_screen_render_ms, turn_raster_p95_ms | 42.45–47.89% |
| simsun / 1.90 / 1552 | 1054.20 / 173.20 / 171.34 | 509.72% | open_including_font_ms, font_load_ms, first_screen_render_ms, page_turn_p50_ms, turn_raster_p95_ms | 49.42–99.78% |

原因判读：environment.json 记录测量开始时其他回归/编译进程，process.json 记录每次系统 CPU 忙碌度。这些后台任务及消息调度是干扰来源；没有独占 CPU 或频率/温度追踪，不能把每个异常值精确归因。首屏与加载计时样本很短，绝对值的少量波动也会超过 10%。按预定顺序保留全部 54 次，不按速度删点。

逐翻页阶段诊断（stages.csv）：1080/1080 次有匹配 SDK ready；input→ready 中位 4.05 ms，ready→present 中位 153.48 ms。因此端到端 p95 不能直接当作字体光栅化耗时。

既有 paint.csv 验收的 miss_p95_ms 是无缓存 SDK pager+render；下表复用该计算，包含翻页间的预取工作。逐次值在 sdk-work.csv。原验收宽度 1280/2560 的 25/35 ms 门槛与本轮客户区不同，不直接套用。

| 字体 | 行高 | 1242 无缓存 SDK p95 ms | 1552 无缓存 SDK p95 ms |
| --- | --- | --- | --- |
| Noto Serif SC | 1.6 | 21.73 | 37.42 |
| Noto Serif SC | 1.75 | 21.65 | 26.00 |
| Noto Serif SC | 1.9 | 29.45 | 44.83 |
| Noto Sans CJK SC | 1.6 | 17.15 | 28.23 |
| Noto Sans CJK SC | 1.75 | 16.69 | 35.05 |
| Noto Sans CJK SC | 1.9 | 14.80 | 20.19 |
| 宋体 | 1.6 | 9.02 | 11.85 |
| 宋体 | 1.75 | 8.57 | 18.50 |
| 宋体 | 1.9 | 8.70 | 16.61 |

## 默认值建议

按预设门槛，18/18 组超过 100 ms，5/18 组超过 200 ms。
超过 200 ms 的配置：sans / 1.60 / 1552; sans / 1.75 / 1242; serif / 1.60 / 1242; simsun / 1.60 / 1242; simsun / 1.75 / 1242。

1552 视口默认衬线 1.75：p95 = 171.97 ms；无衬线 1.75 = 188.11 ms，相对变化 -8.58%。衬线 1.90 = 190.21 ms，页数 1117。

建议保持衬线 1.75 的当前默认值：本轮在共享机器上的三次重复不足以支持为性能下调行高或改回无衬线。超过门槛的配置应保留为性能问题；先复测/定位端到端呈现路径，再决定默认值。本轮没有修改产品默认值。

## 19 本真书回归与范围

**矩阵指定 DLL 的两次独立全量运行**：均为 19/19 本成功、11,061 页、8,648,640 字形；页数变化 0，逐页像素哈希变化 0，内容指纹一致。regression-repeat.json / regression-repeat.diff.json 保存独立复跑及比较；命令在 regression-repeat-command.json。

使用既有基线的原 DLL 重跑：19/19 本成功，11,128 页，8,694,817 字形；变化页数 0，needs_review=False。baseline-regression.json / baseline-regression.diff.json 保存逐页结果，命令在 baseline-regression-command.json。

另以矩阵指定 DLL 全量运行：19/19 本成功，11,061 页，8,648,640 字形；与既有基线有 5872 个共同序号页的像素哈希差异，总页数变化 -67 页，needs_review=True。regression.json / regression.diff.json 保留完整跨 DLL 比较，不将其标为零差异通过。

基线 DLL SHA-256 `57d17c88f2bca6a1b859a456fb5362ac548c830a905e6e83cf76ee5149285bd2`，矩阵 DLL SHA-256 `892ea1acb0a519748d9b51c2f5f946d762b7f78d1015d42f811db3ba8fd18865`。两个 DLL 的输出差异需另行审计；本次提交没有改动引擎、头文件、宿主或 workflow。相对 protocol.json 中构建源码 revision 的受保护目录 diff 为空，未手动触发 CI、未取消 workflow。

## 复现

```powershell
python -X utf8 tools/perf/typography_bench.py selfcheck
python -X utf8 tools/perf/typography_bench.py build --work C:/Users/Oscar/Documents/Codex/typo-bench-work-20261107 --sdk-build C:/Users/Oscar/Documents/Codex/cjk-justify-20261106/build
python -X utf8 tools/perf/typography_bench.py run --work C:/Users/Oscar/Documents/Codex/typo-bench-work-20261107 --output evidence/typography-bench-20261107 --capture C:/Users/Oscar/Documents/Codex/EXReader-typo-20261106/ops/capture_window.py
python -X utf8 tools/perf/typography_report.py
```

重测使用新的 work/output 目录；已有 result.json 的轮次会续跑，未完成目录需先归档。excluded-attempt.json 记录最初中断轮次；该轮全部排除，不参与上述统计。
