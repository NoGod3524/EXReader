# Common raw3 Apple 完整工作流投影

此包仅准备同一源码上的完整 Apple 验收入口，当前没有运行记录，也不授予运行验收。源码基点为 `1a6d98ed613c61ffea4267f01f83e2c49b1c02f6`，共同运行分支为 `codex/reader-raw3-common-integration`，最初开发分支为 `codex/reader-raw3-common-apple`。

| 新工作流 | 原完整工作流 | 原作业与判定 |
| --- | --- | --- |
| `reader-raw3-common-apple-records.yml` | `reader-apple-records-ready.yml` | SDK 两目标、native 19 项、macOS/iPhone/iPad 各原七例、原 strict 与 readiness 复核，共七作业 |
| `reader-raw3-common-apple-macos.yml` | `reader-apple-raw3.yml` | 原实际 macOS owner、兼容全套、12 个 raw 阶段和原 strict，共两作业 |
| `reader-raw3-common-apple-ios.yml` | `reader-apple-raw3-ios-ready.yml` | 原 SDK 两目标、iPhone/iPad 各 OFF 七例/raw 六阶段、原 strict 与 readiness 复核，共五作业 |

原 workflow、driver、裁判、断言、180/300/600 秒预算、readiness 准备与默认 raw OFF 均保留。新增入口只替换工作流名称、实际触发分支、guard 和最终 verify 入口，并增加新 guard 自测与来源 sidecar。records 的五处分支绑定一起替换，所以 SDK 3.41.0/主题 ON 以及旧 SDK guard 的排除条件均针对真实新分支；不改写 `GITHUB_SHA`、`GITHUB_REF_NAME` 或其他 Actions 身份。

`guard.py` 将全部已有文件的 Git blob 与 mode 精确固定到基点，新增集合也必须精确相等；SDK 额外固定至 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，七模块额外固定至 `56793e7ca4f8ecdc5f2d9c3394fce4e201aca275`。三份投影逆变换后必须与基点原完整 workflow 逐字相等。`test_guard.py` 仅在 Actions 执行，覆盖删除原步骤、预算/环境变化、分支/guard 身份变化、已有 blob/mode 改写、缺失与额外文件等拒绝。

## Guard 的真实身份与工件路径

新记录的 `guard_kind=common-source-exact-apple-workflow-projection-v1`、`original_guard_executed=false`。新记录包含真实 source/run/attempt/target、common 基点、冻结 SDK/模块源、原/新 workflow SHA-256 和新 guard 自身 SHA-256。它没有冒充原独立分支 guard 成功。

* records：写入原上传路径 `build/apple-records-ready/guard.json`。原 strict 只读取该 SDK ZIP 的 `build/sdk-identity.json`；新的 strict 包装补验 SDK 两目标各自的 guard。
* macOS raw：写入原 runner 需要的 `build/apple-raw3/guard.json`。原 runner 逐字将其放入 `evidence/guard.json` 并登记文件哈希；原 strict 认证此哈希，新的包装继续认证 guard 内容和来源。
* iOS raw：写入 `build/raw3-ios-sdk/<target>/common-source-guard.json` 并加入各目标原 SDK 工件。文件位于原工件公共根目录内，保持 SDK、产品和 identity 原来的解包相对路径。原 driver 不消费该 sidecar；新的包装认证两个目标的 sidecar。

原 strict 的上游作业和工件总数限制不变。没有另加 producer 工件；macOS 仍只有一个上游工件，records 仍为六个上游工件。新包装先执行原最终裁判，再通过真实 Actions API 元数据、ZIP 字节数/散列/有效期认证新 guard；结果写入各原 summary 目录下的 `common-source.json`。iOS 原 summary 上传列表仅追加这一文件。

共同验收必须同时要求原 summary、原 readiness（适用时）、新 `common-source.json` 和该工作流全作业成功。旧 summary 的 accepted 字段仅代表旧裁判范围，不能单独代替新 guard 认证。

## 交回整合

本轮只本地提交新增源码；未 push、未启动 Actions，未本地构建、语法检查、测试或下载处理工件。

`BRANCH` 与三个新 workflow 的全部对应条件已绑定共同真实分支 `codex/reader-raw3-common-integration`。真实 guard 从 `tests/reader_raw3_common_runtime/combined.py` 纯加载 `EXTENSIONS`，合并本包七文件后逐项比较精确新增集合；不调用 `configure()`，不改 `sys.modules`，基点所有已有 blob/mode 仍必须不变。自测的假树默认继续使用本包 `NEW_FILES`。清单逐项固定，没有目录豁免。三份完整 Apple 工作流继续分开运行，以保留原 strict 对作业/工件数量的要求。

此包不更改产品、SDK、schema 1、wire envelope 1、anchor 1/2 和公开默认 MAX 2。真机、读屏、性能、完整产品与六平台互通均未在本包授予。
