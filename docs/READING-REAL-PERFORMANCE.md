# R3 真实代表语料测量

当前SDK固定为`9854061be331fe603a1822d9b2b36ee357154927`，正式基线起点为
`da1c1833d89932612d8e4549fee5aec378555ad4`。旧SDK `9c69bc4c…` 的失败与旧合成PDF/CBZ、TXT和长章记录保留原身份。
本包不修改引擎；实测缺陷与热点交R4修复后按新源码重验。

## 固定输入与测量口径

唯一语料清单为R2的`tools/reading_corpus/real-v1.json`，只采样预先标记
`performance_representative=true`的真实文档。原件、来源、许可、SHA-256及选定参考页由R2登记；
性能采样不能替代全书兼容验收，也不能抵扣原1710目标或WP16进程CPU时长。

`tests/reading_real/contract.json`固定Ubuntu22.04、Release reading-core、字体、单核亲和性、
新进程5次、连续32页和固定seed随机16次、72dpi白底RGBA、EPUB 800×1000与24px字号。
字体复用`tools/host_font.py`固定的Noto Sans CJK SC/OFL（`2c76254f…`），不把1176字节矩形测试字体授予真实性能基线。
EPUB走有界入口，顺序读取用`next()`明确判断章尾，随机阶段重建独立`get()`缓存模式；跨章及随机重建计入操作耗时。随机操作在该次连续遍历所见的33条part/page路由间重放；
PDF随机操作覆盖整个声明页目录。只测原生引擎到首帧，不包含UI显示、屏幕刷新和进程启动耗时。

每个新进程前读取原件和字体以预热文件页缓存；不宣称冷盘，SDK的解析和页缓存仍从新进程开始。
固定runner标签不表示固定物理设备，报告保留image、CPU和编译器。预算拒绝与基线CPU/编译器不兼容的运行。

RSS为进程high-water，包括字体、解析器、位图、分配器和映射。工作区、章索引、页缓存、检查点与位图单列，
它们存在共享或包含关系，不与RSS相加。体积记录实际链接消费者、安装SDK逐文件大小/散列和动态依赖。
章内工作区/缓存分项仅适用于EPUB。PDF记录打开后的`fixed_directory_bytes`与每次渲染后的
`directory_metadata_bytes`公共目录/元数据量（明确排除provider payload）；PDF内部缓存/工作区缺公共细分观测，
全进程RSS保留整体峰值，不把章内原始零字段作为PDF零分配指标。

PDF预选页使用同72dpi Poppler进行RGB像素对照，保留双方原件PPM、原始命令与stderr。
同引擎同页重绘必须逐像素hash一致；跨引擎差异先作疑点复核，不要求全面领先或逐像素相等。

## 验收出口

`.github/workflows/reading-real.yml`支持push、dispatch及workflow_call，稳定job名为`reading-performance`。
唯一工件名为`reading-real-<run_id>-<attempt>`，报告路径为`reading-real/summary.json`。
源SHA、SDK、run/attempt、语料/契约/预算散列和全部原始输出绑定同一次运行。

第一轮仅为测量基线，`accepted=false`；全部原始数据有效时`measurement_valid=true`。
数值预算和逐参考页像素容差必须基于该轮数据先提交并说明原因，再由后继源码完整运行接受。
不通过扩大阈值让失败候选变绿。没有冻结预算时，workflow_call默认严格拒绝。

### 首份完整有效真实基线

源码 `887e1bb59ef6f28c15824cb7593654f3610f3cef`，run
[39899829270](https://github.com/NoGod3524/EXReader/actions/runs/39899829270)，attempt 1 / job `120238599171`，
云端 completed/success。八份代表文档各五个新进程共40份执行、全部12参考页与同页RGBA/UTF-8/位置签名检查完整通过，
`measurement_valid=true`。`accepted=false`，唯一原因是 baseline_only：数字预算和实际逐页审阅尚未冻结。

唯一工件 `reading-real-39899829270-1`，ID `12478631207`，36,327,926 bytes，
ZIP digest `sha256:c3532b00e70e041855ad2e9050dbfe362c51916140af074218fdb45c0a1052be`，同run/source，未过期。
原始报告为 `reading-real/summary.json`。下表直接摘录该轮CI已算出的p95；连续/随机为单次页操作，RSS为每进程整体峰值。

| 文档 | 首帧p95 ms | 连续页p95 ms | 随机页p95 ms | 峰值RSS p95 bytes |
| --- | ---: | ---: | ---: | ---: |
| Alice | 70.257993 | 30.324859 | 178.271096 | 37486592 |
| Frankenstein | 99.967876 | 30.730825 | 138.916036 | 70905856 |
| Pride | 90.175163 | 39.919791 | 284.146186 | 54939648 |
| Moby Dick | 69.661478 | 28.689379 | 217.669045 | 37486592 |
| IRS W9 | 111.536852 | 104.005470 | 103.937605 | 37486592 |
| NIST AI RMF | 230.813066 | 1163.172272 | 1164.892689 | 153837568 |
| NIST CSF2 | 381.650011 | 153.065702 | 151.691157 | 65052672 |
| NASA Solar System | 1861.622897 | 1122.673626 | 1101.135326 | 95875072 |

Frankenstein/Pride 的超大封面在固定随机路线中各发生一次已计时的owned回退，其他两本EPUB为零。
12页已逐页审阅并登记[本轮JSON](validation/reading-real-pixel-review.json)，
云端run39900884120核原ZIP与完整报告后导出冻结预算，已提交于`11cb054…`。
此基线不授予render parity、严格预算通过或全产品完成。

`tools/export_reading_real_budgets.py`仅在CI核原ZIP、原report、K保护树后输出12页审阅模板；
审阅JSON固定原图SHA、baseline身份及逐页finding，提交后才允许导出数值预算。
严格候选还会核对审阅文件路径/内容SHA与全部12对原图身份，拒绝旧三页记录或未审阅项。

首轮`39887915689`（`f57fb562…`）实际SDK和消费者编译成功，但只有W9的五个进程完整执行；EPUB消费者误将缓存模式章尾当作`OK+NULL`，其余真实文件另有`LIMIT/FORMAT`。整轮失败保留，没有从失败轮冻结预算。
后继修复消费者EOF口径、固定工件布局并增加具体错误诊断；随后以原生宿主固定字体重采样。尚无本包性能通过声明。

`fcfd2b5`的云端`39890300401`进一步证明Frankenstein/Pride拒绝的是`part=0,page=0`封面，
单图解码为19,888,896/12,684,000字节，确实超过原8MiB缓存；这是公开缓存契约的正常拒绝。
尚未冻结性能预算阶段，消费者合同改为显式超大页策略：仅在`get()`返回`EXR_LIMIT`后独立owned顺序重放，
实际页大小必须大于未变的8MiB预算，所有拒绝/重建/重放耗时和RSS计入随机样本，临时页释放。
每条route同时核对顺读与回放的完整RGBA和选定规范UTF-8文本散列；独立反例拒绝未超限、未证明缓存拒绝、
漏计拒绝耗时及route/text变化。保留原纯`get()`失败，不宣称底层缓存接受了超大页。

`aff4dd6a` / 云端`39893185090`已实际编译并执行：25/40个进程完整（四本EPUB与W9各5次），
其余三份PDF仍由旧SDK的stream cache/ToUnicode问题阻断，整轮`measurement_valid=false, accepted=false`。
同轮baseline metadata 1正12反、完整report/ZIP来源2正22反、稳定RGBA/UTF-8/位置错误1正3反、
超大页策略1正5反均通过；这些工具自验不替代缺失的15份真实执行。

正式预算启用时，Actions下载锁定ID的baseline ZIP，核完整digest并保留原始
`reading-real/baseline-summary.json`及`baseline_summary_sha256`。报告必须同source/run/attempt，
`measurement_valid=true`，合同/原件/字体/SDK保护树/CPU/编译器/参考版本与本轮相符；
Git对象逐项核实保护树声明。冻结数值和签名必须来自这份原始报告，预算不能靠自声明拼接。
预先数值推导上界见`tests/reading_real/contract.json`，没有据本轮失败填写或放宽预算。

W9差分审阅及固定原图/诊断身份见[READING-PIXEL-REVIEW.md](READING-PIXEL-REVIEW.md)。
新SDK全部12页已由完整基线实跑、实际审阅并冻结预算；
独立严格执行纳入共同源码`11cb05489839c8587936340d83b4e45e214463d2`的17作业run39901084062，
尚无严格性能通过声明，最终按该次结果登记。
