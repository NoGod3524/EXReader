# V premerge review (no new cloud run)

统计对象固定为 95100501..21add50a，不含本次补充提交。

| 目录 | 增行 | 删行 | 文件 |
|---|---:|---:|---:|
| (root) | 8 | 4 | 2 |
| .github | 28 | 0 | 1 |
| apps | 15 | 54 | 13 |
| cmake | 40 | 2 | 5 |
| evidence | 4270 | 0 | 12 |
| examples | 9 | 6 | 3 |
| include | 9 | 2 | 2 |
| tests | 158 | 17 | 20 |
| tools | 11552 | 34 | 16 |
| 总计 | 16089 | 119 | 74 |

## Generated content and policy data

- tools/version_literal_exceptions.json：11246 增行，逐行用途/证据登记，是受校验的策略输入；初始清单机械整理后附用途与证据，不是可丢弃的构建生成物。
- evidence/sdk-version-20261103/scan-before.json：4082 增行，机器扫描快照。两项合计 15328 行，占增行 95.27%。
- evidence/ 下 JSON/text 为扫描、安装和 CI 观测的机器输出或整理证据，保留原快照，不随当前树覆盖重生成。
- include/exr/version.h：7 增行，入库生成镜像；输入为 cmake/version.h.in 与 cmake/versions.cmake，校验器比较 UTF-8 原始字节。README 的版本行由同步脚本派生，其余正文手写。
- build 内生成的版本头、CMake package/version 文件和 pkg-config 文件不入库。

## Reproduction

```sh
python tools/check_version_consistency.py --sync-generated
git diff --exit-code -- include/exr/version.h README.md
python tools/check_version_consistency.py
python tests/check_version_consistency.py
```

既有 SDK identity CI 已运行上述测试脚本；本次加入模板漂移和换行漂移检查，不新增工作流、不发起运行。测试暂改模板，先断言校验器拒绝，再重生成并断言输出变化，最终逐字节恢复。无输入改动的重生成须与入库头和 README 完全一致。输出见 generated-reproducibility.txt。

## base.h

95100501..21add50a 仅新增 #include <exr/version.h>，EXR_VERSION 从字符串转接 EXR_SDK_VERSION，EXR_ABI_VERSION 1u 移至生成头。剔除这几行后的其余内容逐字节相同：无函数签名、结构体或枚举变化，ABI epoch 1 不变。

## Integration

V → P → C 进入 ledger/base-20261103；R 候选必须是 P 落地后的提交（含 V + provider），不是 21add50a。本次不合并、不触发 CI；native 全矩阵留到 R 候选证据轮。
