# Step 6 真实 EXE 证据

已精确复现 owner 的 `ff3f4377…`：125% 缩放下，未声明 DPI 感知的抓图脚本分配了过小位图。修正 PMv2 抓图后，owner 原始 EXE 与指定 DLL 重编 EXE 的四组完整客户区图差异均为 0px，最大居中偏差 0.5px。

- [完整报告、三个高度与构建命令](../../2A-STEP6-FIX.md)
- [错误抓图原件](real-exe-before-1242x742.png)
- [物理整窗 1242×742](real-exe-1242x742.png)
- [物理整窗 900×600](real-exe-900x600.png)
- [物理整窗 1280×800](real-exe-1280x800.png)
- [三尺寸及精确客户端 1242×711 的机器结果](real-exe-result.json)
- [原始完整图、四组对照图和高度日志](record/real-exe-measurements.tar.gz)
- [实际加载 DLL 路径](record/real-exe-loaded-dll.json)

- [本轮既有 8/8、字号锚点 12/12、直接跳字号 10/10](record/real-exe-regression.json)
- [本轮原始回归测量](record/real-exe-regression-measurements.tar.gz)

本轮记录使用 `real-exe-` 前缀。其他图片、result.json、record/real-* 及历史记录保留自前轮验收；本轮以本页以上链接为准。书籍原件与书库数据库未纳入证据包。
