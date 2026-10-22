# H6：收紧 H1 跨平台证据门禁

执行 [共同约束](reading-extra-index.md#全部包共同约束)。从 H1 文档 HEAD
`2e8e981b6dd44d855a23931480fe5e0d5c791762` 新建 `handoff/reading-h6-platform-gate`。
可立即开工，不重做 H1 的平台方案。

## 文件所有权

仅改 `tools/reading_platform_evidence.py`、`.github/workflows/reading-platforms.yml`、
`docs/READING-PLATFORMS.md`，必要时新增 `tests/check_reading_platform_evidence.py`。
不改现有 Linux 门禁、消费者 CMake、SDK、preset 或 H2 的八份概述文档。

## 必须解决

1. 当前程序参数允许为空、workflow 可跳过不存在程序。按当前消费者 CMake 冻结每个 profile
   必需的精确程序集合，缺少、重复、未知项、空集都拒绝；路径存在还需实际产物身份。
2. Windows `unresolved=[]` 不能表示已验证 DLL 全部可解析。
   明确区分原生工具的依赖名称观测、实际执行过的程序与未执行的程序。
   基准程序未执行时不能写“所有程序均由 loader 成功加载”。
   采用现有程序的安全实际调用或收窄结论，不新增伪运行。
3. 记录 CMake 实际选用的编译器/链接器与版本，核对 Windows MSVC 环境；
   工具路径异常应清楚报告，不凭 PATH 顺序推断链接器。
4. 云端执行最小拒绝回归：必需程序缺失、空集合、重复、错误 profile、错误平台、
   依赖工具失败或原始输出缺失必须拒绝。测试不得仅重复脚本实现。

## 验收与交付

Windows/macOS × 两 preset 四作业在同一新源码运行，保留原消费者及九格式 smoke。
登记逐程序的实际执行状态与来源散列、原始依赖输出、四工件身份。
旧 run `39854485070` 的平台构建成功保留，并注明旧门禁范围；新门禁不追认旧源码通过。
交付固定受测 SHA、新 run、拒绝回归与结果文档。无需设置默认分支 required checks。
