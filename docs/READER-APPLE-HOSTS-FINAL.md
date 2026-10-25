# Apple SDK3.41 共同宿主候选

独立分支 `codex/reader-apple-hosts-final` 从冻结的 `f4aa876c4e077201ade122c6a558a90731327daa` 开始，普通合并初始化/书架发布证据 HEAD `897f8973c1a8c74fa5aaf9a470d02e6914faeded` 与精确 parser 拼写兼容证据 HEAD `e8ed25c1cd7ccb33405611e27f9ad47fba8c9e34`。两次合并无冲突，生产合并基线为 `902a73bd9984649000d63e96d5056b16daf28c85`。

## 同源验收

SDK 生产树固定 `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0 / ABI1 / core3.40.0）；旧 SDK 标识仍为 `9854061be331fe603a1822d9b2b36ee357154927`，模块固定 `f680aeaddfb1ecc67ead353554f5b91a5703f72f`。Apple 生产文件与原消费者、主题 UI、两项确定性导入 UI 逐树固定到生产合并基线。三份 Android Java policy 文件逐 blob 固定到 `b1a7b7891cd394671842164a07a86c8e316dace3`；它们仅提供既有精确 parser 拼写策略，不授予实际 Android writer 互通。

首次 push 仅运行源码身份与 Actions 语法预检。通过后在同一固定 source 派发主题、导航、搜索、阅读记录、书架、导入映射、WP13 七个完整工作流。原六消费者、collector、strict summary 与业务步骤保留；仅候选分支选择由旧隔离分支改为本分支。原默认 3.40/OFF、等待与断言不变。

主题运行新增两项确定性 iPad UI 到自身完整作业图：SDK 必须来自该次运行的 iOS producer，下载 ZIP 字节/散列和安装身份全部核对；严格汇总同时拒绝缺失/失败的新增消费者。旧 `6d53` 或独立 `e6` 的程序和通过数不转授给当前 source。

当前尚未完成该共同源运行；`accepted=false`。

## 保留的历史运行

`f4aa876c` 的七组已全部终态，无需取消：

| 组 | run / attempt | 结果 |
| --- | --- | --- |
| 主题 | 40174318190 / 2 | failure；iPhone 在 Xcode 前的 `simctl ui appearance light` 45 秒超时；SDK、native、macOS、iPad 通过 |
| 导航 | 40174363253 / 1 | failure；iPad 首例首次导入没有 `library.book.0`；严格汇总拒绝 |
| 搜索 | 40174365142 / 1 | failure；iPad 首例首次导入没有书架行；严格汇总拒绝 |
| 阅读记录 | 40174367348 / 1 | failure；iPad 首例首次导入没有书架行；严格汇总拒绝 |
| 书架 | 40174369194 / 1 | success |
| 导入映射 | 40174370909 / 1 | success |
| WP13 | 40174372884 / 1 | success |

主题 attempt1 仍保留；不与 attempt2 拼接。三组失败的其他平台/native 通过记录不构成完整组通过。

只读保留录像诊断 [40181597278](https://github.com/NoGod3524/EXReader/actions/runs/40181597278)，source `6a6d4b85b9bf15932a056081f595d1866dda14eb`，读取原导航失败工件 `12591639142`。5.863、7.947、8.33、10.083 秒实际帧均显示空书架与“就绪”；原点击事件坐标 `(281.75, 898.25)`、窗口 `744×1133`。录像不证明原首次点击发生于初始化窗口，也不证明导入已经提交。独立两项回归证明生产缺口及修复，不代替原失败根因结论。

原六组、真机、旧 iOS 书库、性能及六平台产品互通均以各自实际证据单独授予。
