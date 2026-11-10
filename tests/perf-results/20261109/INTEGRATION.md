# 最终 main 整合验收

已解决与 main `ed252fb6` 的冲突，保留最新的阅读样式、脚注、词典、TTS、书架元数据功能。最新 main 的默认正文是 **1456×752、18px、1.75 行高**（客户区 1552×928），此前基线分支为 612×768、1.6 行高。两组分别保留，没有通过缩小新版正文换性能。

**最终宿主 20 次翻页 p95：14.5317ms / 10.3771ms，均 ≤16ms；空白帧均为 0。** 同步 SDK 连续批量路径仍未稳定达标：合并后最好 13.4526ms，第 11 项首测 13.9672ms，最新重测 **44.1758ms**。不能将偶尔通过的一轮写成同步路径稳定通过。

## 合并后继续逐项测量

每行修改后仍跑 19 本×20 页，380 个像素 hash 全部一致。SDK 未作新的产品修改；波动逐本保存到 `19-books-incremental.csv`。

| 阶段 | 宿主 p50 / p95 ms | 关键分段 p95 ms | Peak RSS MiB |
|---|---:|---|---:|
| 合并 main，保留原 shelf.json 保存 | 13.6873 / 18.4103 | settings 3.6020, compose 8.4140 | 192.707 |
| 10：相同 JSON 跳过原子写入 | 11.8030 / 14.2143 | settings 0.8027, compose 9.4158 | 192.879 |
| 第 10 项复测（长尾原样保留） | 10.3062 / 246.7669 | settings 0.6794, compose 243.6702 | 193.031 |
| 测量采用 buffered trace，细分合成 | 12.8457 / 24.5670 | settings 0.8824, theme 5.7793, footer 5.2859, compose 11.2160 | 193.004 |
| 11：主题灰度精确查表 | 8.3859 / 14.5317 | settings 0.7011, theme 2.0995, footer 3.1334, compose 5.9029 | 192.820 |
| 最终独立复测 | 7.8783 / 10.3771 | settings 0.7416, theme 2.6893, footer 3.1543, compose 6.0774 | 192.961 |

第 10 项宿主 p95 改善 4.1960ms，设置保存 3.6020→0.8027ms。第 11 项在同为 buffered trace 的协议下，宿主 24.5670→14.5317ms；主题着色 5.7793→2.0995ms，合成 11.2160→5.9029ms。查表逐个核对 256 级灰度，明暗两主题、彩色插图与彩色纸张完全保留原字节。

测量脚本的 buffered trace 只用于测试构建，正常退出时落盘；产品原有 logger 不变。此前逐事件 fflush 的 trace 全部保存。最终宿主使用 Release SDK，无 SDK 内部 QPC，输入间隔 400ms，原有预取保持不变；终点为新 generation 的 GDI 提交/GdiFlush，未测物理扫描。

## 同步 SDK 剩余瓶颈与架构要求

最新连续批量 p95 **44.1758ms**，比 16ms 多 **28.1758ms**。该慢帧的非重叠外层计时为：分页+整形 **4.9970ms**，光栅/像素输出 **39.1788ms**，宿主绘制/Present 为 0。同一 Release DLL 的首测为 13.9672ms，证明剩余长尾不能单按固定计算成本解释。线程 CPU 时钟在本机是 15.625ms 粒度，不能据单页读数 0 判定零 CPU。

原始完整五段 QPC、缓存命中率与前九次优化见主报告。SDK 的无预取连续批量契约还没有稳定达到 16ms；下一层需要 **持续存活的页面准备线程 + 有界 ready-frame 队列**，提前完成分页、整形、光栅化和主题处理，呈现线程只提交准备好的帧。当前宿主已有页面预取，本次消除了其空 worker 和 UI 排队开销，宿主结果已达到目标。若同步 API 本身也要求每轮 p95≤16ms，需要用调度/缺页跟踪进一步区分 39.18ms 光栅阶段的 CPU 与等待，再决定 SIMD 混合或内存驻留策略；本轮没有把这部分宣布完成。

## 最终正确性与内存

- **251/251 ctest 全绿**，包括合并后的全部 SDK 测试、7 项 fuzz 和 10 组 Windows 宿主测试；原分支的 228/228 日志也保留。
- **19 本 × 全部页**：720×1040 共 **11,318 页**，1552×928 共 **5,599 页**；两组页数、每一页像素 SHA-256 全不变，glyph 总数均 8,648,571。
- 宿主额外检查通过：未变化 INI/JSON 不写、变化内容正确持久化、无关 JSON 字段保留、准备好的 DIB 不建空 worker、全部灰度与彩色纸张字节一致。
- 同为新版 main 正文：峰值 RSS **192.707→192.961MiB**（最终两轮取较大值，+0.254MiB / +0.13%），峰值 commit **168.031→168.781MiB**。旧版正文的前九项比较是 177.379→177.273MiB；不能把升级 main 带来的正文/功能内存算成缓存增幅。
- 分层检查：118 objects，0 新增反向引用，0 反向 include。没有新增 src 头文件，没有修改 `.github/`。

最终全书比较以 `integration-realbooks.diff.json`、`integration-target-realbooks.diff.json` 为准；`integration-ctest.log`、`integration-host-checks.log`、`integration-layers.log` 和 `integration-provenance.json` 对应合并后的最终配置。

在主报告的构建步骤中，额外开启 Windows 宿主检查：

```powershell
cmake -S . -B build/full -DEXR_BUILD_FUZZ=ON -DCMAKE_PROJECT_EXReader_INCLUDE=C:/Users/Oscar/Documents/Codex/EXReader-perfopt-20261109/examples/windows/selection_tests.cmake
cmake --build build/full --parallel 4
ctest --test-dir build/full --output-on-failure -j 4
```

独立 `perf_host_checks.c` 的链接命令需要再加入生成目录下的 `speech.o`，以覆盖最新 main 的 TTS 组件。
