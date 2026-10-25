# Android SDK3.41 整页主题候选

状态：指定 API34 default x86_64 模拟器范围通过；受测源码 `57bc3966c20171f2f51e3fc6bf02f1ad1f7e5165`。

本候选起自 Android 导入证据 `8a564e817fec01538d9c6efc35d173c6f24d8fec`，普通合并 SDK3.41 `edddc463c06ed5731195cdb8f06b2df6dff7699e` 和模块显式版本支持 `f680aeaddfb1ecc67ead353554f5b91a5703f72f`；之后的路径归属基点为 `82ca471c867209f48d3c07eaf92baf0eee57c74b`。

构建显式传 `-PexrPageTheme=true`，默认关闭。原始配色默认开启，继续使用原先分页/绘制；取消“原始配色”后才使用选择的浅色、深色或系统主题。系统外观在 UI 线程采样为不可变输入，所有 SDK document/font/pager/layout 仍由现有串行 worker 创建、绘制与释放。

TXT 和非有界 EPUB 使用宿主所有的公开 SDK 对象，几何、文本范围和原始 RGBA 来自同一 layout。TXT 返回的页面文本逐字节与该 document 的规范化投影切片核对。EPUB 有界路径继续使用现有 publication/pager。主题通过布局默认前景 CSS 与 `exr_render_page_background` 原生绘制；没有截图或位图重染。作者背景、书籍图片和固定 PDF/CBZ 保留原色。

设置仍使用原 F3 包，准备新页与精确 FOUND 位置后才保存并替换会话。系统外观事件只更新显示，不重写 F3、SDK 进度/笔记、产品修订或 outbox。忙时保留最新事件；过期外观采样、取消、失败或旧 Activity owner 无法发布候选。原始配色是宿主本地偏好，与 F3 文件分开保存；不声明跨文件掉电原子性。

旧 120 项业务检查保留。F3 原 17 项的候选副本仅把两个明确颜色缺口用例替换为实际深色页面/系统深色正向断言，其他检查名与逻辑保留。HostSync 的运行版本预期明确从 3.40.0 改为 3.41.0。Actions 保存全部候选预期差异及原脚本 SHA；原测试源不改。

新增 10 项实际宿主检查覆盖 TXT/EPUB 的 light/dark/system、Original、原生翻页、可见文字的 bookmark/highlight capture/resolve、作者背景/PNG 真实布局内部采样、固定页原色、取消、I/O 失败、外观连发与新进程恢复。工件保留实际应用原始 PNG、RGBA、原始报告、布局盒坐标与源图片中心像素；严格作业独立认证 ZIP API 字节/digest、像素与报告身份。

Android 实际 parser 标签仍为 `exreader-sdk-3.41.0`，未改旧 formatter、resolve guards 或 wire。不授予 3.40 旧记录迁移、六平台互通、真机、辅助技术或性能范围。

## 同源云端证据

Run [40178247177](https://github.com/NoGod3524/EXReader/actions/runs/40178247177)，attempt 1：Android producer `121123515486` 与 strict summary `121126256838` 均 success。新主题 10/10，原 HostImport20、HostSync16、Search15、Navigation18、Reading16、F3 Preferences17、CBZ10、FixedPan8 共 120/120 同轮通过，总计 130。

实际安装 SDK `3.41.0`；宿主仅依赖一个 `libexreader.so`，实际导入 `exr_render_page_background`；旧 3.40 公开头编译新入口被拒绝。宿主 APK SHA-256 为 `a90a9cbb9e3c8c7441a2d6b7863ad0b2958b2857836f55b41fe451a98f808a68`。原导入的 9 个不同 PID、4 处真实持有边界强杀、3 APK 安装字节绑定及 fsync/原子 ready 协议全部保留并由 strict 独立核对。

| 工件 | ID | 原 ZIP 字节 | SHA-256 |
| --- | --- | ---: | --- |
| Android 全证据 | 12593940382 | 131405024 | `1e0f4b7945798b326931684dd8ffdb2863d1f4ebac1a9121f25d46a8e02479ea` |
| strict 汇总 | 12593485972 | 1105 | `cc2ce21b544774e52239703e7b9f566ab52cbfc21c513f505a5484d31bb09eea` |

有效期均为 `2027-01-23T08:50:53Z`。strict 实际下载 producer 原 ZIP，核对 API 大小/digest/source/attempt/producer 结果后才读取报告；逐帧验证原 PNG 解码字节等于原 RGBA、声明散列、整页角点与实心前景像素、实际布局内部的作者背景和图片色。

新增主题两个进程 PID 为 `2454` 和 `2785`，分别 9 项与 1 项通过。11 张实际 600×860 页面中，TXT dark/light 的实心目标前景各 11506 像素；EPUB dark/light 分别 10932/10929。三张 EPUB/legacy 页面均在实际背景盒内部 `(118,194)` 保留 `e0b070ff`，图片内部 `(72,237)` 保留 `1478dcff`。这些数量是本轮原像素观测，未设性能预算。

6 组真实可见范围的 bookmark/highlight capture/resolve 均 FOUND，保留实际 `exreader-sdk-3.41.0` 标签。设置、取消、I/O 失败、受控旧 OS 采样拒绝、最新事件合并以及新进程系统深色恢复均检查了实际页面或保存字节；原 UI 和产品状态检查未以截图颜色代替。完整 check 名、工件和 formatter/guard blob 身份见 [验收 JSON](validation/reader-android-page-theme.json)。本地仅编辑、Git 与只读日志/API metadata，构建、语法检查、夹具、运行及工件下载/解析全在 Actions。

## 保留的失败

- `f7025b6b` / run `40176117979`：宿主与原生审计通过；旧导入20、HostSync16、搜索15通过。目录第三项发现列表 ready 先于首行真实布局发布，随后已修宿主批量换页/复位/布局就绪发布，原18项测试不变。
- `5aa59af5` / run `40176912569`：Original 与独立旧公开绑定的实际像素逐值对比通过；TXT 深色实际前景像素失败。TXT 没有 HTML body，已改为在公开段落模型上应用前景规则；原生整页背景已是真实目标颜色，不能据此授予整页主题。
- 根共同源 run `40175058872` 的旧 FixedPan 第二项保留为未收口：真实 pointer/timer 尚未形成有效选区。当前原8项断言和注入事件不变，候选只增加失败时实际 pointer/hit/anchor 与 frame 诊断，继续用同源整轮验证。
- `271a1856` / run `40177552847`：新增首阶段 9/9 已通过，runner 却误要求 instrumentation 正常结束后进程仍存活；改为明确记录已自动退出或尚待外部 stop，并继续要求两阶段 PID 不同。`828f782e` / run `40178167022` 在已知同一 runner 问题后取消，没有授予。

根共同源后续 run `40177143143` 以及本候选最终轮的原 FixedPan 均通过，但不据此声称已经消除旧间歇性输入/观测问题，失败与诊断继续保留。
