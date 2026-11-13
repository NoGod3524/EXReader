# 包 C：WP16 证据审核、兼容分类和最终汇总

先读 `docs/RELIABILITY-SPLIT-HANDOFF.md`，遵守其基线、保护文件、分工与证据约束。建议分支 `codex/wp16-release-audit`，尚未创建。

本包分准备与最终验收两阶段。准备可与A/B并行；最终通过结论等待A+B合并、常规CI通过和源码固定。现在不要再启动96片最终长测。

## 可立即做的工作

1. 读取 `docs/RELIABILITY-HANDOFF.md` 第6节和 `docs/FUZZING.md`，核对严格汇总、证据schema、CPU纳秒和所有拒绝条件。
2. 查询native run `39521329265`终态，保留已有Linux ASan/UBSan通过证据及macOS失败；不能将整体run写成通过。
3. 核验四包原交付证据与主线新证据的源码/散列对应关系；不改原交付JSON和参考图。
4. 复核EPUB/PDF分类记录，区分完成、资源限界、超时、声明外能力、参考修复和待审查；不能因分类完成就把真实书籍整批标为接受。
5. 审核SDK产物、许可证、默认/裁剪安装消费、精确版本C++消费、新接口符号和四类宿主报告。将旧源码结果和待最终重跑项明确分开。
6. 汇总文档中的旧版本/旧run/pending须按对应批次保留或准确补新记录，不把新结论追写到历史源码。

## 证据入口

- 总账：`docs/validation/2026-10-20-parallel-integration.json`，当前current_run过时，需核对新run后更新。
- 交接查询：`docs/validation/2026-10-20-handoff-status.json`。
- 独立审计脚本：`C:/Users/Oscar/exr/build/wp7-integration-20261020/audit-native-artifacts.py`，未受版本控制，接手时先核对内容。
- 原始根：`C:/Users/Oscar/exr/build/wp7-integration-20261020/`。
- `accepted-smoke-e265/`：当前引擎源码四入口短测及60秒字体CPU证据；不是24小时验收。
- `rejected-smoke-b4/`、`cross-source-refusal.json`：原失败与真实跨源码拒绝证据，保留原件，只引用路径。
- `reference-r3/reference.json` 与 `reference-cleanup/comparison.json`：56场景固定参考及当前输出RGBA一致性检查。
- `epub-classification/classification.json`：500条，483 baseline完成、11原超时、5资源限界、1引擎参数失败，accepted=false。
- `pdf-classification-r2/classification.json`：122条、73重放；49完成、54参考完成而主引擎拒绝、8参考修复、4待审查、7不支持，accepted=false。

原语料：EPUB `C:/Users/Oscar/exr-corpus-v1/gutenberg`；PDF `C:/Users/Oscar/exr/tests/corpus`。不得覆盖原结果或为提高通过率删除条目。

## 最终集成与验收顺序

1. 接收A/B完整提交SHA和报告，顺序合并；统一组件版本与文档，记录准确引擎/包源码。文档提交与引擎来源须有明确关系。
2. 执行联合常规native CI，7/7同源码通过。三平台非插桩转换报告均要原32 MiB预算通过；ASan报告不得替代。
3. 下载全部16类artifact到新的独立目录，保留API元数据、run状态与散列。审计脚本当前硬编码3.39.0等版本及本地许可基线，版本变化时显式更新预期，不能直接跳过断言。
4. 核对六SDK配置/六平台、许可、默认/裁剪消费、符号和版本；四宿主Windows/macOS/iPhone模拟器/iPad模拟器分别26/21/21/21项按对应源码报告核对。真机暂缓，不能写为已通过。
5. 验证四入口真实短测并对下载后的附件严格重汇总，再冻结干净源码运行最终长测：parser/font/layout/render各24片×3600 CPU秒，最多8片并行。
6. 每目标至少86,400秒真实进程CPU。缺片、失败、失联、不足时长、重复有效种子、跨源码、清单/程序/运行库/语料散列不一致、附件缺失或篡改、上游失败均拒绝，不累计失败片CPU。
7. 发现问题先保留证据、修复并加回归，再按新源码重定验收；不能跨源码拼接出24小时。
8. 对下载后全部报告进行本地严格汇总，更新WP16逐项清单；所有真实门槛满足后才标记本轮完成。

## 原长测处理

run `39451039706` 固定在f719bd4旧源码。交接前有字体runner失联，缺有效报告CPU计0。保留历史现场，按run终态处理恢复；不要重启重复96片，也不要将其算入最终源码验收。更早失败run `39370107827` 同样保留。

## 文件分工与交付

本包负责最终证据与 `docs/HANDOFF.md`、`docs/RELIABILITY-HANDOFF.md`、`docs/NATIVE_VALIDATION.md` 总结；准备阶段先写独立审计JSON，避免A/B同时写总账。必要的可靠性工具修复集中于 `tools/run_reliability_campaign.py`、`tests/check_reliability_campaign.py`、`.github/workflows/reliability.yml`；native工作流修改与A协调。

交付提交SHA、源码/run/产物清单、严格汇总结果、兼容分类、每个仍未满足条件。完整WP12和其他路线包的完成状态不因本轮WP16工作自动改变。
