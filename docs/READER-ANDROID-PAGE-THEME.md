# Android SDK3.41 整页主题候选

状态：实现与 Actions 验收脚本已准备，尚未获得云端通过。

本候选起自 Android 导入证据 `8a564e817fec01538d9c6efc35d173c6f24d8fec`，普通合并 SDK3.41 `edddc463c06ed5731195cdb8f06b2df6dff7699e` 和模块显式版本支持 `f680aeaddfb1ecc67ead353554f5b91a5703f72f`；之后的路径归属基点为 `82ca471c867209f48d3c07eaf92baf0eee57c74b`。

构建显式传 `-PexrPageTheme=true`，默认关闭。原始配色默认开启，继续使用原先分页/绘制；取消“原始配色”后才使用选择的浅色、深色或系统主题。系统外观在 UI 线程采样为不可变输入，所有 SDK document/font/pager/layout 仍由现有串行 worker 创建、绘制与释放。

TXT 和非有界 EPUB 使用宿主所有的公开 SDK 对象，几何、文本范围和原始 RGBA 来自同一 layout。TXT 返回的页面文本逐字节与该 document 的规范化投影切片核对。EPUB 有界路径继续使用现有 publication/pager。主题通过布局默认前景 CSS 与 `exr_render_page_background` 原生绘制；没有截图或位图重染。作者背景、书籍图片和固定 PDF/CBZ 保留原色。

设置仍使用原 F3 包，准备新页与精确 FOUND 位置后才保存并替换会话。系统外观事件只更新显示，不重写 F3、SDK 进度/笔记、产品修订或 outbox。忙时保留最新事件；过期外观采样、取消、失败或旧 Activity owner 无法发布候选。原始配色是宿主本地偏好，与 F3 文件分开保存；不声明跨文件掉电原子性。

旧 120 项业务检查保留。F3 原 17 项的候选副本仅把两个明确颜色缺口用例替换为实际深色页面/系统深色正向断言，其他检查名与逻辑保留。HostSync 的运行版本预期明确从 3.40.0 改为 3.41.0。Actions 保存全部候选预期差异及原脚本 SHA；原测试源不改。

新增 10 项实际宿主检查覆盖 TXT/EPUB 的 light/dark/system、Original、原生翻页、可见文字的 bookmark/highlight capture/resolve、作者背景/PNG 真实布局内部采样、固定页原色、取消、I/O 失败、外观连发与新进程恢复。工件保留实际应用原始 PNG、RGBA、原始报告、布局盒坐标与源图片中心像素；严格作业独立认证 ZIP API 字节/digest、像素与报告身份。

Android 实际 parser 标签仍为 `exreader-sdk-3.41.0`，未改旧 formatter、resolve guards 或 wire。不授予 3.40 旧记录迁移、六平台互通、真机、辅助技术或性能范围。
