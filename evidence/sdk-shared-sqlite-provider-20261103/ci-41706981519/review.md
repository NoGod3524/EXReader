# 限时构建验证结果：红，转已知问题

- 候选：`64e514ae396ee73d37c72d732c21e99d1dc3b816`；父提交 `40ac811b0a872587641e01ff0cfc33a376e93abc`；SDK 内容基线 `95100501eeef9c6325be8b3882aa400c99cf000f`。
- [Run 41706981519](https://github.com/NoGod3524/EXReader/actions/runs/41706981519)，attempt 1，job `126164781176`，macos-14，单作业，上限 20 分钟。
- 作业 2026-11-03 19:50:22–19:50:34 UTC；结论 failure。当时未自动重试；后续第 2/2 次已获用户明确授权。
- 分类：**限时构建验证失败；构建配置失败，非行为失败**。不计入共享 provider 验收，不是 Apple 验收通过。

## 首条错误

```text
2026-11-03T19:50:30.3063920Z fatal: bad object 95100501eeef9c6325be8b3882aa400c99cf000f
```

首个 GitHub error 标记为 `Process completed with exit code 1.`，根因错误是上面的 `bad object`。
候选在 `95100501` 上已有两层后续提交，checkout 仍配置 `fetch-depth: 2`，只取得候选与父提交，未取得基线对象。
固定基线范围检查因无法读取对象而停止；这是本次 workflow 配置遗漏。检查没有被跳过或放宽。

## P 包 CI 卫生项 CI-ADMISSION-001

归属：P 包 CI 卫生；不进入 F07 已知问题清单。
状态：open，原运行停止；用户随后批准准入修复后的第 2/2 次限时构建验证。
影响：源码准入未完成；provider/SDK/ProductCatalog 构建、两个原产品测试、联合 FTS5、真实 Apple 内嵌负例全部未执行。
后续参考方案：显式取得固定基线对象，或使用足以覆盖完整已审查提交链的历史深度，并先检查基线对象存在；保留固定基线、固定候选和路径核对。
本原始运行没有修改后重跑。后续修复与授权记录见 `../ci-hygiene-CI-ADMISSION-001/review.md`。

## 四项证据

本次四项均没有新增有效结果：无符号表、无 FTS5 执行结果、无 stage、无真实 Apple 内嵌负例结果。
原产品测试 `product-originals` 与 `native-product-catalog` 未执行。

**两项仍待 CI**

`artifacts.json` 的 API 返回为空列表。上传步骤因没有任何输出文件而失败，未产生工件，不能写作“已保留产物”。
完整解码作业日志保存在 `job.log`，run/job metadata 在 `run.json`，文件哈希进入顶层 `artifact-sha256.json`。
首次运行的原始 ZIP 与日志仍保留在 `ci-41705105811/` 所指位置。

catalog、测试断言、SDK 版本与默认分支均未修改。构建项未关闭，SDK 共享 provider 验收未完成。
