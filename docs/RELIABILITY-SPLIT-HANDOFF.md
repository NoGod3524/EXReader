# 2026-10-20 可靠性续批分工交接

## 接手入口

用户将本轮实施移交给其他 AI。本交接整理现场，不新建会话、不启动智能体或新 CI；已有远端作业继续运行。接手方先核对当前状态，避免重复实施。

- 仓库：`C:/Users/Oscar/OneDrive/文档/ChatGPT/EXReader`。
- ASCII 入口：`C:/Users/Oscar/exr`，指向同一仓库。
- 当前分支：`codex/framework`；交接代码基线：`07c6910c12dab572771440c7ce34157f079f80d9`。
- 引擎/包源码上一提交：`e265cf462523da35ffb37b4ff3a38cc3b7bb13ff`；07c6910 仅增加转换内存诊断工作流。
- SDK/core/PDF/library：3.39.0 / 3.38.0 / 3.38.2 / 3.34.0；ABI1 / schema6。
- WP7、WP8、WP12-lite、WP12a 已集成、提交并推送；不要再次 cherry-pick 原交付提交。
- WP6 有界章内解析、最终源码长测及 WP16 最终汇总仍未完成；完整 WP12 另行跟踪。

先读 `docs/RELIABILITY-HANDOFF.md` 第6节、`docs/HANDOFF.md`、`docs/NATIVE_VALIDATION.md`。上述文档包含历史现场；当前续批状态还须结合本交接和 `docs/validation/2026-10-20-handoff-status.json`。

## 三包分工

| 包 | 接手文档 | 可立即开展 | 等待条件 |
| --- | --- | --- | --- |
| A | `docs/HANDOFF-CONVERSION-MEMORY.md` | macOS 转换内存根因、修复、专项和四包跨平台集成 | 最终联合验收需合入 B |
| B | `docs/HANDOFF-WP6-BOUNDED-CHAPTERS.md` | 章内有界解析、恢复、固定语料量测 | 最终联合验收需合入 A |
| C | `docs/HANDOFF-WP16-RELEASE-AUDIT.md` | 证据核验、兼容分类复核、拒绝条件与发行清单准备 | 最终长测及通过汇总等待 A+B 合并、源码固定 |

A、B 的预期修改面不同，可以并行；不能保证未来发现的根因不会涉及共同核心文件。需要跨包文件时，先把最小改动和目标提交交给该文件负责人协调，不在共享目录同时修改。C 的最终通过结论存在依赖，不能算完全独立包。

建议分支名：A `codex/reliability-convert-memory`；B `codex/wp6-bounded-chapters`；C `codex/wp16-release-audit`。这些是约定名称，尚未创建。各方从上述基线建立独立工作树、构建目录和证据目录；不要同时在 `codex/framework` 工作目录开发。

共同文件的负责人：A 维护 `.github/workflows/native.yml` 和转换工具；B 维护文档/分页核心及其回归；C 维护最终发行证据和汇总文档。根 `CMakeLists.txt` 如需共同修改，各包只交付自己的最小片段，由集成人顺序合并。版本统一由最终集成人处理。

## 已知 CI 和现场

- 完整 native run `39521329265`，源码 e265cf4：交接快照为 Windows/Linux/Android/fuzz/sanitizers 通过、macOS 失败、apple-mobile 运行中。接手后重新查询终态。
- macOS 专项 run `39521983620`，源码 07c6910：已失败，四种分配器配置均未通过原内存预算。四份原始 JSON 已下载。
- 最新查询快照、四组量测和散列在 `docs/validation/2026-10-20-handoff-status.json`。
- 原始证据根：`C:/Users/Oscar/exr/build/wp7-integration-20261020/`。其中 `macos-memory-diagnostic-r1/` 保留四份诊断 JSON。
- `docs/validation/2026-10-20-parallel-integration.json` 的 current_run 和 pending 字段尚未追上最新 CI，不能直接作为当前终态。
- 旧长测 run `39451039706` 属于源码 `f719bd4590df4dfb7ef04b5ac5a58d49a7b9a310`，不能移用于当前四包或后续 WP6。

## 固定约束

1. 保留所有原始失败、交付证据和量测。不得扩大内存/CPU预算、参考容差或删减固定场景来过验收。
2. 不把已接受的脚本/字体/轻量转换/媒体声明边界重新扩成额外功能出口。
3. 非插桩 Release 三平台转换仍要求100项批处理峰值不超过单项峰值+32 MiB，计量不得为零，临时文件为零。
4. ASan 执行相同100项功能及泄漏检查；其 RSS 只能记录为插桩量测，不能替代产品预算验收。
5. 所有 CPU 长测要求同源码、干净构建、真实报告、程序/运行库/语料散列。失败、失联、缺片 CPU 不计入通过时长。
6. iPhone/iPad 真机安装按用户要求暂缓；模拟器与真机分别记录。
7. 对外只引用文件路径，不粘贴崩溃栈、fuzz 输入细节或攻击性描述。
8. 两个未跟踪文件不可修改、删除或提交：
   - `docs/validation/2026-10-19-shading-extent-ci.json`，SHA256 `a955abda1e35fd456172b2e78e1d687799e4ab5f1f977dec0efd7684aae9fdc1`。
   - `src/internal.h`，SHA256 `c951b04a1611008b2e97437d6877bebabf29ec2c374a1c8166c9aca14f34e904`。
9. Windows 外部 C 工具和参考 renderer 使用 ASCII 路径；Python 使用 UTF-8。不要清理其他工作树。

## 统一交付与合并顺序

每包交付分支、完整提交 SHA、文件清单、准确源码对应的验证 JSON、原始证据目录、失败/未完成项。默认只提交本包，不自行合并其他包或改写主线。

A、B 各自验证后交集成人顺序合并；C 核对最终源码、统一版本和文件散列，跑联合常规 CI。七作业全部通过后才冻结最终验收源码并启动4目标×24 CPU小时长测；最后按严格拒绝条件审核下载后的报告和产物。源码再次变化时，重新判定验收来源，不混用旧报告。
