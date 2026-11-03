# CI-ADMISSION-001：P 包 CI 卫生

归属：P 包 CI 卫生，不进入 F07 已知问题清单。原 `SDK-BUILD-002` 分类撤销，以本编号为准。
触发 run `41706981519` 的首条错误是 `fatal: bad object 95100501eeef9c6325be8b3882aa400c99cf000f`。
准入检查依赖固定基线的完整历史，但 job 原配置仅 `fetch-depth: 2`，没有声明所需的完整历史。

## 单独的 CI 卫生修复，供 P 复用

1. checkout 显式使用 `fetch-depth: 0`；对已有浅克隆，可在准入前 `git fetch --unshallow`。
2. 比较前执行 `git cat-file -e <固定基线>^{commit}`，对象不可读则停止；保留固定候选、父提交和路径准入检查。
3. 本地先从普通 `--depth 2 --no-checkout` 浅克隆复现，再补齐历史并验证 `git cat-file -e 95100501eeef9c6325be8b3882aa400c99cf000f` 成功。原始日志在 `plain-*.log`。

最早的 partial-clone 探针启用了 `--filter=blob:none`，其 cat-file 可通过 promisor 获取对象，不能作为普通 checkout 缺历史的负例；该探针原始日志 `shallow-before.log`、`baseline-before.log` 保留。正式先验采用上述不带 filter 的普通浅克隆。

## 明确的消费者契约事实

**C++17 仅测试目标需要，对外契约未变，SDK 消费者不需要 C++17。**

本次新增的 C++17 声明只在测试目标；ProductCatalog 的内部实现此前已有 PRIVATE C++17 要求。
安装后 C++98 消费者编译、链接、运行及导出目标核对记录在 `../limited-build-preflight/`，SDK C11 核心和公开 C 接口未变。

## 当前授权

用户推翻此前“不再跑”，批准本次限时构建验证第 **2/2** 次：macOS-14 单作业、上限 20 分钟、不自动重试。
修改 workflow 需新候选 push 生效，因此“2/2”为用户授权轮次，GitHub 新 run 自身的 `run_attempt` 另按 API 原值记录；不把旧 workflow 的直接 rerun 当修复验证。
绿色只关闭 Apple build-only 项，run id 与实际产物入 evidence；不写成完整 Apple 验收通过。
若因新原因红，只记首条 error、转 open item，不再申请。

首次 run `41705105811` 仍分类为“构建配置失败，非行为失败”，不计入共享 provider 验收。
原状态原文保留：**两项仍待 CI**。真实后续执行结果另记。
