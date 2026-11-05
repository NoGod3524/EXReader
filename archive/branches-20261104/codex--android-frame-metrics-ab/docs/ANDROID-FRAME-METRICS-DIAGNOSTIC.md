# Android 窗口帧时诊断（2026-10-23）

整轮 `comparison_interpretable=false`、`accepted=false`。A1 原仪器化超时，不能用其余三轮补成 ABBA 比较通过。本轮不授性能预算、真机流畅性或产品完成结论；不阻塞已经独立通过 required 的 PR5 产品库接入。

## 源码、配置和计量

- 生产依据：`c9870ed68df539b2f08cb889817cd81b3e2e8a6b`；独立诊断分支 `codex/android-frame-metrics-ab`，实际采集源码 `f2273c952e0fb3931eed11e0a6f25006d02ac826`。
- 同一个新诊断 debug APK 运行四轮。A 为显式 `View.LAYER_TYPE_NONE`（0），B 为 `View.LAYER_TYPE_SOFTWARE`（1）；未使用硬件缓存层。没有配置时，源码仍选择 c987 的 SOFTWARE 默认值。
- 通过专用 `Settings.Global` 键配置 phase/mode，穿过原脚本的 `pm clear` 和进程重启；每轮独立启动 probe、每个实际 trace 的头均核对 phase、mode 和实际 layer type。A1 probe 已观测 NONE/0，B1/B2/A2 的所有实际 trace 也分别观测 SOFTWARE/1、SOFTWARE/1、NONE/0。
- `Window.OnFrameMetricsAvailableListener` 在专用 HandlerThread 的回调中立即复制 `FrameMetrics`；每个 PID/真实 Window 实例单独 JSONL，使用递增回调序号，记录 `TOTAL_DURATION`、VSYNC、各阶段、首帧标志和回调丢失数。
- 普通帧按 `FIRST_DRAW_FRAME == 0` 单独汇总 `TOTAL_DURATION`，nearest-rank 分位数；首帧另列，不跨轮合并。TOTAL PSS 由外部每秒按实际 PID 采样。
- 计量对象是已交付回调的 Activity Window；不代表独立 ReaderView 耗时或显示器实际呈现时间。原45项脚本包含等待、截图、对话框及主动终止进程；强制结束边界可能尚有未交付回调，不声称全过程帧数普查。诊断回调和写文件开销同时存在于两种模式。

## 同一采集运行的实际观测

[run 40014169649](https://github.com/NoGod3524/EXReader/actions/runs/40014169649)，attempt 1，job `120621849665`，最终 failure。平台为 API34 default x86_64 模拟器、pixel_6、4 cores、4096 MiB，刷新周期 `16666666 ns`。

| 轮次 | 原45项 | 普通帧 | p50 / p95 / p99（ms） | TOTAL 超刷新周期 | PSS 样本 | PSS 中位 / 峰值（KiB） |
| --- | --- | ---: | --- | ---: | ---: | --- |
| A1 / NONE | 未完成 | 缺失 | 缺失 | 缺失 | 无可授予结果 | 缺失 |
| B1 / SOFTWARE | 45/45，0失败0跳过 | 515 | 85.289197 / 299.133800 / 466.868892 | 99.4175% | 182 | 61953 / 109491 |
| B2 / SOFTWARE | 45/45，0失败0跳过 | 505 | 82.168458 / 281.846289 / 492.240338 | 98.4158% | 180 | 61963 / 90724 |
| A2 / NONE | 43/45，2失败0跳过 | 506 | 71.875597 / 296.543709 / 435.456447 | 99.2095% | 175 | 54624 / 99817 |

B1/B2/A2 各有6份真实 Window 文件、3个 PID；回调丢失数均为0，文件与回调序号校验成功。其外部采样均无错过采样槽、无采样器异常、无失败 PSS 请求、无采样 PID 缺少 trace。首帧分别20、23、22份，未混入普通帧分位数。重新读取本 run 原始 JSONL 和 PSS 样本后，逐项重现了上述原统计。

A2 的两项失败仍为 `process_restart_reflow`、`pdf_process_restart`。NONE 即使出现更小帧时，也不能据此回退其已有像素正确性问题。SOFTWARE 两轮功能通过，但 PSS 峰值差异较大，A1又缺失；目前不能给出稳定的额外内存成本，也不能把这些窗口 TOTAL 分位数称作真机流畅性结论。

## A1 的有限原件回读

A1 的配置 probe 成功，记录18次回调、实际 NONE/0。随后原仪器化仅保留340字节的测试开始状态，stderr为空；900.002617秒后本地 runner 上的 adb 客户端按既定900秒预算超时退出。901个 PID 采样均未观测到阅读器进程。

超时后的 APP trace 拉取失败，本轮没有留下 A1 的逐项设备用例、实际采集 trace 或设备 logcat dump。原因未获证明，不能归因于渲染器、FrameMetrics 回调或某个具体用例。整轮报告的 boot/display 不完整拒绝包含 A1 终点缺失，并不证明设备实际重启或刷新周期改变。

本次只做一次有界云端原件回读，不盲重跑整轮 ABBA。原始失败及拒绝保持不变。

## 身份和保留物

原 run 工件 `12529481022`：452653024 B，SHA-256 `78ce0b37ba5afc30617e3ed566b12f5e5193652a63e9132efe98477459a9ab23`。原上传日志与 API 的 ID、名称、字节数、digest、run/source 一致。

只读回读：[run 40018234993](https://github.com/NoGod3524/EXReader/actions/runs/40018234993)，attempt 1，源码 `77117a5d506b55199f736f8cfa2302f699e4656e`，job `120635764222`，success；`audit_completed=true`，仍 `accepted=false`、`comparison_interpretable=false`。工件 `12528818480`：286709 B，SHA-256 `6634fae8ca1e36e40faac3fecbdaf18f07028131352a0d02b975a192bb56c5be`，上传与 API 一致。内含来源 API、原 ZIP 校验收据、A1原始输出/采样和三轮逐字节 JSONL/PSS/用例记录。

诊断 APK：22276785 B，SHA-256 `b83342a5653ac9ca79b9db40443fd4833711a81a4b01438bcb388097ac5d6026`。这是新的诊断二进制，不是原 c987 APK；其全部 assets、字体和完整 native 登记与原 c987 工件逐字节相同：

| 原件 | SHA-256 |
| --- | --- |
| Reader.otf | `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b` |
| lib/x86_64/libexreader.so | `4d112a889433aaff0396c1c052091a37ad65b8f892818e7b4d92ea04e69d7fa6` |
| lib/x86_64/libexreader_host.so | `015e5d6fb6d5b709ec5ee67caf4f64e19e2a311a21bec662e7bd072227b3abe8` |
| lib/x86_64/libexreader_jni.so | `0010ab3b811f1d5f7839d2770062f129a71c7745ee6ddafbb22210fe6d520c15` |

原45项 helper/test APK 原样复用，未改断言或 SDK，未重编译 native。本地仅源码、文档和 Git；编译、运行、语法检查、工件下载与解析均在 GitHub Actions。

早先 gfxinfo ABBA 的拒绝也继续保留：其窗口身份不足且字段不稳定，无法用于本轮比较。旧字段审计不证明发生了同一真实 Window 的后置更新；本轮也不把旧采样数值拼入新观测。
