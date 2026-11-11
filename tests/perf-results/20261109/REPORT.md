# 最终交付状态

已合并最新 main。客户区 1552×928、紅樓夢、20 次翻页，最终宿主 p95 **14.53 / 10.38ms**，空白帧 0。同步 SDK 连续批量路径尚未稳定达标，最新 p95 **44.18ms**（合并后最好 13.45ms），剩余瓶颈与架构要求见 [最终整合验收](INTEGRATION.md)。

最终 **251/251 ctest**、两种版式全部 **19 本 / 11,318 + 5,599 页**逐页 hash 一致；新版 main 同版式峰值 RSS **192.707→192.961MiB**。下方为合并 main 前的完整五段基线与前九次优化历史；后两项、最终版式、复测长尾和最终证据均记录在整合验收中。

<!-- historical-record -->
# 翻页性能证据 · 2026-11-09

Windows 宿主客户区 1552×928、紅樓夢、20 次翻页：两轮 Release SDK 复测 p95 **13.1492ms / 11.2258ms**，空白帧均为 0。宿主保留原版式：正文 612×768、18px 字号、1.6 行高；没有缩小内容或降低质量。输入间隔沿用现有 typography 驱动的 400ms，原有 150ms 预取保持不变。计时终点是首个新 generation 的 GDI 提交/GdiFlush；不是物理屏幕扫描完成。

同步 SDK 整张 1552×928、24px、margin=48、line-height=1.5、paragraph-spacing=10 的 Release p95 三轮为 **13.8715 / 13.6805 / 14.1768ms**，全部 ≤16ms。下文分开记录这两个调用契约。

## 83.19ms 的来源与五段计时

仓库内可追溯的 83.1915ms 位于 `evidence/perf-gate3-20261108/ROOT-CAUSE.md`，是 CPU3/HIGH、19 本×16 页的 pooled SDK 指标（720×1040），不是单本紅樓夢的 Windows 输入到显示提交指标。旧记录没有这五段的 QPC trace，无法逆推出历史 83.19ms 的精确分摊。

先在未改产品的 d9ffdbf0 上构建 QPC 探针。最初自由调度的同尺寸 SDK 实测 p50=80.8253ms、p95=112.5608ms；随后固定 CPU3/HIGH，原 DLL 重测 p95=42.4503ms。下表保留两次基线，后续 SDK 比较均固定 CPU3/HIGH，保留系统 Balanced 电源方案；时钟/调度仍会波动，最终用交错复测核对收益。机器为 Intel Core Ultra 7 256V，Windows x64，GCC 16.2 Release。

单位 ms，每格为 p50 / p95。分页列已扣除嵌套 inline shaping；raster 包含像素分配、清底、字形装载、FreeType 光栅化和混合。字形装载/FT 子计时保存在 JSON，不能再加到总数。

| 五段 | 原始自由调度 | 原版 CPU3/HIGH | 最终 CPU3/HIGH |
|---|---:|---:|---:|
| 分页/布局（扣除整形） | 3.5168 / 26.6201 | 2.3677 / 3.7688 | 1.4065 / 2.5248 |
| inline shaping / GSUB / GPOS | 17.7123 / 49.9608 | 14.6122 / 16.0838 | 3.5608 / 4.5561 |
| 光栅化/像素混合 | 52.3250 / 74.4544 | 22.7968 / 24.7740 | 5.3926 / 7.0250 |
| D2D 宿主绘制 | 0 / 0（SDK 无此调用） | 0 / 0 | 0 / 0 |
| Present / vsync 等待 | 0 / 0（SDK 无此调用） | 0 / 0 | 0 / 0 |
| 总时长 | 80.8253 / 112.5608 | 39.6425 / 42.4503 | 10.3409 / 13.7840 |

边际分位数不能直接相加。总时长 p95 对应的同一页，五段相加分别为：

- 自由调度原版：4.8737 + 41.0144 + 66.6727 + 0 + 0 = **112.5608ms**。
- 固定调度原版：1.9281 + 15.7482 + 24.7740 + 0 + 0 = **42.4503ms**。
- 固定调度最终：2.5248 + 4.2342 + 7.0250 + 0 + 0 = **13.7840ms**。

原版最大的 SDK 段是 raster（固定调度 p95 帧占 58.4%）。页游标 `exr_pager_next → next_page` 已经增量推进，没有每次重排整章，因此没有改分页算法。原版有 advance/metrics 缓存，20 页 64,128 命中 / 2,163 未命中；没有可复用的整形结果或字形位图缓存。

宿主另有 QPC 时间线：原版固定调度 input-to-submit p50/p95=251.3906/389.3468ms，D2D EndDraw=120.0872/148.8941ms；最终 Release 第 2 轮分别为 8.6330/11.2258ms、1.3078/1.4691ms。EndDraw 包含 D2D 提交和等待，API 计时不能把 GPU 执行与 vsync 再拆开。宿主没有 DXGI Present 调用，不能套用 DO_NOT_WAIT。测到的 UI 阻塞也并非全是 16.7ms 的整数倍：重复 INI 写入 p95=102.3864ms，以及缓存命中后仍创建空 pixel worker 的排队等待是独立来源。

## 每项完成即重测

每次都运行 19 本×20 页，逐页像素 SHA-256 全部相等；完整逐书 p50/p95/max 在 `19-books-incremental.csv`。下表为紅樓夢 p95。1 为自由调度，2–9 为 CPU3/HIGH。1 的 SDK 不含产品修改；其调度噪声不算改进。主机的长尾原样保留，未删除失败于性能目标的轮次。

| 次序 | 单项变化 | SDK p95 ms | 宿主 p95 ms |
|---|---|---:|---:|
| 1 | 标题不变时停止重复使标题栏失效 | 150.0491 | 291.3756 |
| 2 | 每字体 1MiB 字形位图 LRU | 35.9280 | 2139.8798 |
| 3 | 短文本整形结果缓存 | 29.6267 | 36.7654 |
| 4 | 灰度字形先裁剪，再连续混合 | 28.0063 | 123.8486 |
| 5 | 只写入变化的 INI 设置 | 29.1842 | 69.4871 |
| 6 | 整形上下文键使用实际 joining 类别 | 26.1739 | 57.3552 |
| 7 | 已有原尺寸 DIB 直接排队完成，省去空 worker | 25.9231 | 17.3980 |
| 8 | 已接受的帧立即 UpdateWindow，避免排在存储消息后 | 26.2991 | 13.8247 |
| 9 | 整形缓存从 256 增至 1024 槽 | 13.7840 | 13.1492 |

固定调度 SDK 基线 42.4503ms → 35.9280（字形缓存，−6.5223）→ 29.6267（整形缓存，−6.3013）→ 28.0063（混合循环，−1.6204）→ 29.1842（宿主改动，SDK 波动 +1.1779）→ 26.1739（上下文键，−3.0103）。这些历史轮次包含时钟/调度波动，最后一项另做未插桩的交错对比。

第 5 项将 settings_save p95 从 102.3864ms 降到 0.9778ms。第 7 项宿主 57.3552→17.3980ms（−39.9572），第 8 项 17.3980→13.8247ms（−3.5733）。第 9 项整形缓存命中从 23,483/36,670=64.04% 提高到 29,118/36,670=79.41%；字形位图命中 19,419/21,573=90.02%，FT_Render_Glyph 由 21,573 次降至 2,154 次。

两轮预先安排的 Release SDK 复测：

| 轮次 | p50 | p95 | max | 空白帧 | Peak RSS MiB | Peak commit MiB |
|---|---:|---:|---:|---:|---:|---:|
| 原版同条件 | 251.3906 | 389.3468 | 409.2359 | 0 | 177.379 | 153.285 |
| 最终 1 | 8.4951 | 13.1492 | 21.6730 | 0 | 177.273 | 152.738 |
| 最终 2 | 8.6330 | 11.2258 | 38.4845 | 0 | 177.070 | 153.230 |

RSS 没有显著上升；字形 LRU 上限包含元数据，整形每 face 最多 1024 项，每项最多 64 glyph / 256 UTF-8 bytes；随字体销毁。字形缓存保留取消检查和工作预算收费。整形缓存按完整文本核对哈希、返回独立输出副本，自定义 feature/progress callback 走原路径。

## 全书正确性

两组都是 19/19 成功，无页数变化、无任何逐页哈希变化；总 glyph 均为 8,648,571。720×1040 共 11,318 页，1552×928 共 5,599 页。`*.json.gz` 保存前后每一页的 SHA-256；`*.diff.json` 保存比较结果。

| 书籍 ID | 720×1040 页数（前=后） | 1552×928 页数（前=后） | 哈希变化页 |
|---|---:|---:|---:|
| a-raisin-in-the-sun | 356 | 182 | 0 |
| between-the-world-and-me | 228 | 102 | 0 |
| black-boy | 1016 | 475 | 0 |
| born-a-crime | 502 | 230 | 0 |
| crying-in-h-mart | 524 | 237 | 0 |
| how-does-it-feel-to-be-a-problem-being-young-and-arab-in-america | 493 | 232 | 0 |
| i-know-why-the-caged-bird-sings | 625 | 269 | 0 |
| pachinko | 1248 | 646 | 0 |
| the-absolutely-true-diary-of-a-part-time-indian | 560 | 439 | 0 |
| the-autobiography-of-malcolm-x. | 279 | 279 | 0 |
| the-distance-between-us-a-memoir | 702 | 357 | 0 |
| the-fire-next-time | 189 | 77 | 0 |
| the-fire-this-time-a-new-generation-speaks-about-race | 333 | 185 | 0 |
| the-house-on-mango-street | 182 | 121 | 0 |
| zami-a-new-spelling-of-my-name---a-biomythography | 646 | 299 | 0 |
| hongloumeng-24264 | 1686 | 719 | 0 |
| xingshihengyan-24239 | 1202 | 504 | 0 |
| tangshi300-52323 | 83 | 37 | 0 |
| kusamakura-japanese-vertical-writing | 464 | 209 | 0 |

## Release 验收与交错复测

为避免把探针/时钟差异计入优化，增加未插入 SDK QPC 的 Release 测量；JSON 的 `phase_detail=false` 表示 layout 包含 shaping，shape/counter 的 0 代表未采集。第 8 项 Release 首测 17.8912ms；随后以旧、新、新、旧顺序交错运行 19 本，紅樓夢结果：

| 顺序 | 缓存槽数 | p95 ms |
|---|---:|---:|
| A1 | 256 | 14.9423 |
| B1 | 1024 | 13.6805 |
| B2 | 1024 | 14.1768 |
| A2 | 256 | 15.2202 |

第 9 项独立 Release 首测 13.8715ms，连同 B1/B2 三轮全部通过。最保守取三轮中较慢的 **14.1768ms**，距 16ms 留有 **1.8232ms**；最快为 13.6805ms。A1/A2 的波动说明此前插桩 26.2991ms 与未插桩 17.8912ms 的差值不能全部归因于 QPC。各次使用新字体/新 pager，全部 380 页 hash 相等。19 本逐书数据都保留；19 本并非都 ≤16ms，硬性能验收对象是紅樓夢。

最终 QPC p95 帧的阶段分摊在上表；光栅/混合仍是最大段。更高速翻页或去掉预取的宿主压力测试，后续应优先检查 paragraph/itemization 缓存与像素 span 混合。本轮两条既定契约已通过 16ms。

## 验证与复现

`step9-ctest-228.log`：最终缓存配置 228/228 全绿（含 EXR_BUILD_FUZZ=ON）。`layers.log`：0 新增反向符号依赖、0 反向 include。新增整形检查覆盖 CJK/Arabic/ZWJ/ZWNJ 上下文、字号、样式、输出所有权与取消；`tests/perf_host_checks.c` 验证相同 INI 值不改时间戳、变化/空值仍写入、已有 DIB 不创建 worker。

性能构建启用 PDF/JPX、audio/MP3、library/index；ICC、PDF crypto 与可选 WebP/TIFF/AVIF 为 OFF，沿用本机可复现基线的依赖。完整 ctest 构建开启 ICC、PDF crypto、fuzz；可选 WebP/TIFF/AVIF 仍 OFF，228 个测试全部登记。两次 Release 宿主复测使用未插入 SDK QPC 的 `build/perf/libexreader.dll`，宿主保留测量钩子。新建的输出目录避免 trace 追加；JSON 分位数采用 nearest-rank，20 页 p95 为第 19 个值。

在基线 d9ffdbf0 与候选分别构建 Release，再使用相同的 19 本 corpus、Reader.otf 与宿主 seed-profile（library.sqlite）运行：

```powershell
python tests/perf_page_turns.py build --build build/perf --output build/probe-candidate
python tests/perf_page_turns.py sdk --dll build/probe-candidate/libexreader.dll --output build/candidate-sdk.json
python tests/perf_page_turns.py sdk --dll build/perf/libexreader.dll --output build/candidate-release-sdk.json
python tests/perf_page_turns.py host --dll build/perf/libexreader.dll --output build/candidate-host
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/perf/libexreader.dll --font ../exr-demo-2a/Reader.otf --layout tools/regress/layout.json --source-revision candidate --output build/candidate-full.json --baseline build/baseline-realbooks.json --workers 3
cmake -S . -B build/full -DEXR_BUILD_FUZZ=ON
cmake --build build/full --parallel 4
ctest --test-dir build/full --output-on-failure -j 4
python tools/check_layers.py build/full
```

`--font`、`--manifest`、`--seed-profile` 可指定本地资产位置。最终全书比较以 `step9-*.diff.json` 为准；此前轮次的结果同时保留。SDK 完整版式由 `layout-target.json` 保存；原宿主版式与输入序列在 `*result.json.gz` / `*run.drive.gz` 中。`provenance.json` 保存各阶段探针源码/二进制的 SHA-256。测量脚本与原始产物留在 tests 中，不引入产品性能埋点或公开 ABI。

完整开关和 Release 编译选项见 `build-options.json`。宿主额外回归在生成 `build/candidate-host` 后运行（结果见 `host-checks.log`）：

```powershell
gcc -O2 -DEXR_READER_WINDOWS_SHELL=1 -Iinclude -Iexamples -c tests/perf_host_checks.c -o build/candidate-host/checks.o
g++ build/candidate-host/checks.o build/candidate-host/d2d.o build/candidate-host/epub.o -o build/candidate-host/checks.exe -Lbuild/perf -lexreader build/perf/_deps/expat-build/libexpat.a build/perf/_deps/miniz-build/libminiz.a -ld2d1 -ldwrite -lgdi32 -lcomdlg32 -lshell32 -lole32 -loleaut32 -luuid -luiautomationcore -lpsapi -lm -ladvapi32
./build/candidate-host/checks.exe
```
