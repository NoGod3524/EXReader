# 原生 PDF/CBZ 初始测量（R3）

本包在 `reading-core` 安装后静态链接的独立 C 消费者上测量，不依赖 WebView。
基线祖先为 `b529513b7e8e8992786f8c679c0ec6c92110b035`。

## 固定工作负载

| 输入 | 字节 | 页数 | SHA-256 |
| --- | ---: | ---: | --- |
| `tests/fixtures/pdf-color/shading-axial.pdf` | 655 | 1 | `e0b8b52aa4780a3edb036f88a26f5e84997b90ce97bfdcf741ccb8ba7d09a6ee` |
| `tests/fixtures/comic.cbz` | 908 | 4 | `08df7ceb8771ab82610651c2299072b8fc299d3f8fba3996ee6e12054ea6701f` |

这两份为既有 MIT 合成正例，预期页数来自 `test_fixed_pdf.c`/`test_cbz.c` 和阅读 smoke 契约。
不计入真实语料数。PDF 仅包含简单渐变，CBZ 是极小图片页，不能据此推算真实大书性能。
PDF 随机计划因仅一页退化为第一页重画；CBZ 才覆盖多页寻址。
已知混合成功/拒绝页面的 `pdf-public.pdf` 未被列为整本成功性能案例。

字体固定为 `tests/fixtures/fonts/primary.ttf`，SHA-256
`ce360aed7a09322e2c815ed9c06ce9e3304cdfb886b19493e9e59216d622bfed`。
固定 scale=1、白底、RGBA，每次 `exr_fixed_render()` 自然页面尺寸，沿用 SDK 渲染质量，无降质开关。

每个案例默认三次独立原生进程。每次打开字体与文件、读取目录、绘制第一页、顺序重画所有页，
再用 seed=20261022、LCG `state=state*1664525+1013904223`（32位）生成16个页号。
有序页遍历后的随机重复访问属于同一文档的热访问；磁盘缓存未控制，无丢弃 warmup。
进程内最多256页、图像单边4096px，runner最多10次重复，每次默认120秒。
这些是测量任务资源上限，不是产品性能预算。

## 数据与证据

`tools/reading_pdf_benchmark.c` 只使用安装 SDK 的公开 API，记录 monotonic 毫秒、Linux `getrusage`
进程 RSS 高水位、目录 owned bytes、实际页数、每次页号/尺寸/像素字节数/耗时。
`render_ms` 仅包住 `exr_fixed_render()`，不含像素散列和 bitmap 释放；首次可见总耗时包含字体打开、
文件打开、目录、首绘及散列/释放，不含进程启动。RSS 包含字体、SDK、图像及 probe 工作区。
进程内每个实际页面的活跃 RGBA 行用 FNV-1a64 计算一致性散列；它不是密码学散列或独立正确性 oracle。
顺序、随机和跨进程的同页尺寸/像素散列必须一致。没有与成熟引擎做像素差分。

runner 保存每次 stdout/stderr、退出码、超时、SHA-256；失败不删除或筛掉。
只有全部样本有效、相同版本、源码/二进制/字体/输入/工具前后身份一致且源码干净，才输出各指标中位数。
随机耗时每进程以 nearest-rank 求 p50/p95，再在进程间取中位数；不拼接样本。
编译器版本、系统/CPU、编译环境、SDK及消费者的 CMakeCache/compile commands 随云端工件保留。
输出目录不可覆写，任何失败均不得用其他源码结果补足。

## 云端复现

工作流 `.github/workflows/reading-pdf.yml` 构建安装 SDK、构建独立消费者、执行证据负例与原生失败报告检查，再测量。

```sh
cmake --preset reading-core
cmake --build --preset reading-core
cmake --install build/reading-core
cmake -S tests/reading_pdf -B build/reading-pdf-consumer -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK="$PWD/build/reading-core/stage"
cmake --build build/reading-pdf-consumer --parallel 4
python3 tests/check_reading_pdf_measurements.py --binary build/reading-pdf-consumer/reading-pdf-benchmark
python3 tools/measure_reading_pdf.py build/reading-pdf-consumer/reading-pdf-benchmark tests/fixtures/fonts/primary.ttf build/reading-pdf-measurements --source-sha "$GITHUB_SHA" --compiler cc
```

当前未设硬预算；真实多页 PDF、嵌入/回退字体、复杂图像/透明度、大书峰值和跨平台性能仍待独立测量。
本包不授予 WP16、真实语料或整体性能达标结论。
