现有宿主独立验收和 SDK 包不足以授予 F01/F03/F05 的最终六端范围。本 PR 补齐可重复的安装包原生双客户端测试：子书架/分类/系列及成员删除恢复、离线并发编辑与墓碑、取消确认后的幂等重传、实际终止进程后的事务恢复。删除后检查实际墓碑/移除，恢复后逐行匹配原数据。

新 Actions 在 Windows/Linux 编译、运行新测试和原生 HTTPS 故障套件，并重跑宿主基线；Android/macOS/iPhone/iPad 只登记 build-only，产物已下载核对散列。Android 构建驱动补齐导出归档和已安装 SDK 精确版本传参。

验证：本机完整 Release 编译成功；全量 CTest（仅排除 sdk-release/sdk-doc-coverage）581/581；新增三项集成测试 3/3、15 个具名阶段。Actions Windows/Linux 分别 581/581、580/580；两端新增 3/3 + store 2/2，真实 HTTPS 各 20+21 全通过，GTK UI 基线 20/20。prepush exit 0。

Windows 旧 A/B/C UI 验收失败：新 Shell 字号状态与旧检查字段不一致，并有标注跳转/计数、重开状态失败；完整 Windows UI 未验通过。当前专用 iPhone/macOS 作业仍排队；iPhone 使用产品源码路径无差异的前一实际构建，macOS 使用与当前提交完整 Git tree 相同的 PR merge 构建，身份区别已记录。

F01/F03/F05 全部保持 pending；固定分母 108、计数 99/1/8。完整验收引用、历史失败、逐平台缺口、原始输出、产物散列及仅三项台账 diff：`evidence/dfinal-a/REPORT.md`。需要真机或完整宿主 UI/传输的缺项没有转授通过。Draft PR，base main。
