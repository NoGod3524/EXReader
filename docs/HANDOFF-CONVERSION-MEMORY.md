# 包 A：转换内存修复与四包平台集成

先读 `docs/RELIABILITY-SPLIT-HANDOFF.md`，遵守其基线、保护文件、分工与证据约束。建议分支 `codex/reliability-convert-memory`，尚未创建。

## 目标与现场

修复 macOS 非插桩转换工具的100项批处理峰值超限，保留原单项+32 MiB门槛。完成转换工具相关三平台专项，并收口 WP7/WP8/WP12-lite/WP12a 当前声明范围的跨平台集成。WP6 由包 B 负责。

源码已集成，勿重做交付包。完整 CI run `39521329265` 的 sanitizer 已通过；整体未通过，macOS 内存仍失败。Apple 作业交接时还在运行。

专项 run `39521983620` 的四种配置全部失败，原始文件位于 `C:/Users/Oscar/exr/build/wp7-integration-20261020/macos-memory-diagnostic-r1/`：

| JSON | 单项峰值 B | 批处理峰值 B | 增量 B |
| --- | ---: | ---: | ---: |
| default.json | 27,656,192 | 142,753,792 | 115,097,600 |
| aggressive.json | 28,999,680 | 169,574,400 | 140,574,720 |
| nano-off.json | 27,557,888 | 182,321,152 | 154,763,264 |
| both.json | 27,459,584 | 157,941,760 | 130,482,176 |

100项均完成且未报告转换失败。分配器环境没有解决问题。诊断工作流使用 set +e，不能凭工作流结论代替逐份 JSON 检查。

## 重点路径

- `tools/convert.c`：run_job、verify_text_output、批处理循环与所有权。
- `tools/convert_io.c`、`tools/convert_io.h`：平台 RSS 与文件 I/O。
- `tests/check_convert_benchmark.py`：固定语料、单项/100项峰值门槛、插桩报告。
- `tests/check_convert_cli.py`：37个CLI场景。
- `tools/generate_conversion_corpus.py`：固定语料生成。
- `.github/workflows/conversion-memory.yml`：macOS 诊断。
- `.github/workflows/native.yml`：常规七作业和三平台转换报告 artifact。
- `docs/CONVERSION.md`、`docs/validation/2026-10-20-parallel-integration.json`。

现有 cv_release_unused_memory 在每项返回后调用 Darwin malloc_zone_pressure_relief(NULL,0)。本次量测显示它未使预算通过；保留或删除应由根因和实测决定。

## 执行顺序

1. 查询并归档上述两个 run 的终态，核对下载附件的完整性；不要重跑已有四组诊断。
2. 区分真实对象保留、分配器驻留和计量问题。可加阶段/逐项诊断，记录原 RSS；不能直接换成更好看的指标。fork/exec 高水位继承目前只是待验证假设。
3. 从打开→导出→发布→回读校验→释放追踪所有权，根因若落入包 B 的文档核心，先交付定位和最小修复协调共同文件。
4. 用最小改动修复根因，先运行 macOS 专项，再做三平台非插桩预算与必要的全量/ASan回归。
5. 保存新的独立证据，不覆盖任何 rejected 目录。七作业联合发行验收由最终集成人在 A+B 合并后执行。

## 验收

- 相同固定语料、100项逐项释放；Release Windows/Linux/macOS 均满足批处理峰值≤单项峰值+33,554,432 B。
- peak非零、未完成0、失败/拒绝0、残留临时文件0；原始JSON及工具/运行库散列齐全。
- ASan仍执行相同功能和泄漏检查；报告 instrumented=true、memory_budget_evaluated=false、memory_budget_passed=null，不能据此宣称预算通过。
- CLI37项、转换矩阵520项、preserve渲染20项、默认/裁剪消费按现有固定口径通过；共享核心改动需扩大到完整回归。
- 不丢弃原失败，不调整32 MiB门槛，不把单独设置CI环境当成产品修复。

本地 Windows 原通过证据：`build/wp7-integration-20261020/memory-bench.json`。完整源/日志对应关系以原JSON为准。

## 交付

提交SHA、根因和修复说明、三平台JSON与原始日志路径、剩余门槛。新增本包证据使用独立文件，例如 `docs/validation/conversion-memory-followup.json`。最终总账由包 C 合并，避免同时改写共享总账。不要启动最终96片长测。
