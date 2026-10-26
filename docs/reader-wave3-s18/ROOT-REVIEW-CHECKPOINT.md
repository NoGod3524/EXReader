# S18 root review 工作移交检查点

用户要求改由六个独立对话并行，当前停止继续编辑并封存本地 WIP。**未推送、未启动 CI、未运行任何本地构建/语法/测试。此源码修复尚未通过验收。**

- worktree：`C:/Users/Oscar/.codex/worktrees/reader-wave3-s18-root-review/EXReader`
- branch：`codex/reader-wave3-s18-root-review`
- 起点：原 S18 文档 HEAD `0860724c`，受测业务 source `4af92ba023aa64b3ca6db993f2c7b9cec208e326` / run `40247961052/1`。
- 原 S18 worktree `C:/Users/Oscar/exreader-wave3-20261025/worktrees/S18` 未编辑。

## 已写的最小修复

1. `runtime.py` 在 RT 的 `s16/` 子目录按旧 S16 相对布局收齐九实际角色程序、baseline/default/raw 三实际库和三个头、三套 original 原 report+summary、raw 原 report+summary、default summary。保存原 helper 所需的真实 source/run/attempt/platform 与九 role 映射；没有伪造 API 身份。
2. `bindings.py`：Linux/Windows 直接导入原 `tests/reader_next_s16/check_artifacts.py.complete_bindings`；macOS 复制同一函数，只改函数名和 native magic 谓词为 Mach-O，其他 report/程序/归档/头/默认投影/能力符号判定保留。另直接复用原 `check_problems` / `binding_problems`，接收 strict 已认证的实际 API ZIP 记录。原 S16 文件未修改。
3. `strict.py` 调用独立绑定；移除“任取前九程序”等通用损坏控制，改为原九 role 散列、三实际库内容、三 original summary 外来 source 的 **9+3+3 原语义**。旧 S18 的 15 项只是同数量通用文件损坏，不能记为原 S16 控制等价。
4. `consumer/ImportedPaths.cmake` 展开当前实际所需的 `$<TARGET_PROPERTY:EXReader::…,INTERFACE_INCLUDE_DIRECTORIES>`，递归检查/拒绝循环，再以原 canonical path / 声明前缀判定检查全部展开路径。其他生成表达式直接拒绝。`consumer/CMakeLists.txt` 不再跳过任意 `$<…>`。
5. runtime / strict 增加 `--s16-only` 入口：真实 producer 仅 prepare/sdk341/shared/families/graph/jump；明确 `full_joint_runtime_accepted=false`。不重放 sdk340/font/annotation/original/view 业务。独立严格层只授予 S16 绑定和 imported path 再验收范围。

## 尚未完成，接任者先处理

- 尚未做完整静态通读、语法/构建/测试，不能据此认为 WIP 可运行；这些执行仍仅 Actions。
- 计划中的最小路径负例尚未写：已知 TARGET_PROPERTY 正例、其展开到 foreign 前缀、未知 CONFIG 表达式、引用循环。直接针对现有 ImportedPaths helper 即可，不必新造通用协议层。
- `bindings.verify` 应补核 focused scope 的 raw/default 总数分别 162/21；当前已复用原具名检查、身份/报告/程序绑定及 default accepted/mode/version 判定，但 focused 分支没有复用全量 strict 上已有的这两个精确总数断言。
- `runtime.finalize` 新增 validation_scope/full_joint_runtime_accepted，但原 `scope` 描述仍固定为 full joint business replay；focused 模式应同步改为准确的限定描述。
- 新 workflow/输入尚未改，现有 workflow 默认仍调用完整 runtime/strict。**不得直接推送并默认重跑完整安装图。** root 先审阅，再决定最小有界实际执行入口。
- 原 S18 已实际通过的普通三桌面业务重放范围保留；缺失旧三库/原报告不能从旧 summary 反推或用合成协议补授予。
- 若 root 批准再跑，最小 producer 集合为三桌面各一组 prepare/sdk341/shared/families/graph/jump，加一个绑定 strict。共同图需安装其依赖包，但无需重复其他四模块业务测试；所有新结果单独归属新 source/run/attempt。

## 同代理此前任务交回

### 格式组合和独立 SDK 候选

- 格式组合 source `8015c576822d5284dedfea17428ecf1a240befd0`，run `40244430230/1` success；证据 HEAD `0d330c3bdc027a4b9b42b8f402675c13f43a96c1` 已推送。
- SDK 源码候选 `9d3a3f8bfa06c099ebba0d9e1ba613d276c3af09`，唯一父批准 SDK `edddc463c06ed5731195cdb8f06b2df6dff7699e`；只改 `src/rtf.c`、`src/cbz.c`。
- SDK whole tree `dd5f4fa912bcaab483524a76988515c731f22702`、src tree `001bd8d0baa49ecde6fae82d799bafd0b007030f` 与组合受测隔离候选逐字一致。
- 文档 HEAD `4a64ad917fa030b5af7e4f190c1b3394556ac5d4`；worktree `C:/Users/Oscar/.codex/worktrees/sdk-341-format-adoption/EXReader`，branch `codex/sdk-341-format-adoption`。未推送、未新 CI，保持独立不动，SDK 尚未采用。

### C11 固定 WIP 只读审查

固定 source `d941ba0fd5aa6badbfe10a11fac8837fbbce5f28` 的五项问题已交 root，由原承接者修复，不应在其 worktree 并写：

1. product JNI annotationImport 活跃域回调 Java resolver，再由 readingBook→NativeCatalog.lookup 重入同 product owner，必遭 active reentry 拒绝。
2. 原件导出取消时 HostTask.check 留 pending Java exception，roe_run 返回 receipt 后却先 new_rows/FindClass，直到最后才检查异常。
3. 将整个批量 annotation commit 包入 HostTask.commit，令其中 cancel/check 失效。
4. 暂存 ok=true 后的取消检查及 readingCall action 返回后的检查，会遗留 .part 或已 rename 的私有文件。
5. JumpPanel 关闭后直接丢弃过期结果回调，已 peek 的 native token 无 drop，复制 wire 保留至清历史/关书。

本检查点不表示这些 C11 问题已修复，也不影响其承接者后续源码身份。
