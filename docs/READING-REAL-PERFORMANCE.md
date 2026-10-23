# R3 真实代表语料测量

SDK固定为`9c69bc4c7efb0cff68ced27562709fe597189041`，工作起点为
`9bd2b2c3caf1f63dc4437e0af978247494e87145`。旧合成PDF/CBZ、TXT和长章记录保留原身份。
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

PDF预选页使用同72dpi Poppler进行RGB像素对照，保留双方原件PPM、原始命令与stderr。
同引擎同页重绘必须逐像素hash一致；跨引擎差异先作疑点复核，不要求全面领先或逐像素相等。

## 验收出口

`.github/workflows/reading-real.yml`支持push、dispatch及workflow_call，稳定job名为`reading-performance`。
唯一工件名为`reading-real-<run_id>-<attempt>`，报告路径为`reading-real/summary.json`。
源SHA、SDK、run/attempt、语料/契约/预算散列和全部原始输出绑定同一次运行。

第一轮仅为测量基线，`accepted=false`；全部原始数据有效时`measurement_valid=true`。
数值预算和逐参考页像素容差必须基于该轮数据先提交并说明原因，再由后继源码完整运行接受。
不通过扩大阈值让失败候选变绿。没有冻结预算时，workflow_call默认严格拒绝。

首轮`39887915689`（`f57fb562…`）实际SDK和消费者编译成功，但只有W9的五个进程完整执行；EPUB消费者误将缓存模式章尾当作`OK+NULL`，其余真实文件另有`LIMIT/FORMAT`。整轮失败保留，没有从失败轮冻结预算。
后继修复消费者EOF口径、固定工件布局并增加具体错误诊断；随后以原生宿主固定字体重采样。尚无本包性能通过声明。
