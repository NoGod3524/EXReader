# 第二批16个独立任务：共同约束

实现起点固定为 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，来自产品候选 `codex/reader-reading-v2`。
交接文档提交只增加本目录，不把该基线所有能力当成新包通过证据。不要跟随移动HEAD。

## 分发与所有权

前6包交给Claude Code，用户指定Sonnet5.5 / Medium；后10包交给DeepSeek Harness，用户指定DeepSeek V4.1 Flash 1017 / High及PTC模式。每包独立会话、分支与工作树。
模型/模式只有界面实际显示才登记已配置，不得悄悄替换。所有任务接受root协调，禁止修改别人的工作树。

所有包能从上述基线独立开始，彼此无实现依赖。功能包不依赖本轮其他新模块；测试/审计包只验证自己的受测source，不能替未来集成或宿主新代码背书。
G01独占Windows宿主接入。G02-G06只新增自己模块；G07-G16只新增测试/工作流/文档。其余已有owner仍负责iOS账号会话、Android会话、Apple书架、GTK接收和F2导航。

## 不变项

- SDK固定K=`9854061be331fe603a1822d9b2b36ee357154927`，SDK3.40.0、ABI1。以下路径逐字不改：`src/`、`include/`、`cmake/`、顶层`CMakeLists.txt`、`tests/fixtures/`、`bindings/`、`.github/workflows/native.yml`、`.github/workflows/reliability.yml`。
- 产品schema1、既有wire v1、reading anchor v1/v2和原数值预算/CPU基线不改。不得读SDK私有SQL、使用本机SDK行号作全局身份或引入新同步实体。
- 只修改本包文件清单。每包另有唯一 `tests/reader_<slug>/**`、`.github/workflows/reader-<slug>.yml`、`docs/READER-<SLUG>.md`、`docs/validation/reader-<slug>.json`，具体以任务页为准。本交接目录由root维护，代理不修改。
- 生产模块独立CMake、安装后公共组件和C ABI，默认reading构建不加入。复用现有实现，不引入WebView、JS UI、新服务器、插件框架或重复解析器。
- 所有构建、测试、语法检查、夹具生成、benchmark、服务和工件下载/解析仅在GitHub Actions。本地仅源码/文档/Git；不运行Python parse、编译器或本地测试。
- 不改默认分支/保护规则，不合并PR，不建tag/Release、不正式签名发布，不使用真实账号秘密或用户私人文档。测试CA只存在Actions临时runner/模拟器信任库。
- 构建或测试失败由原实现/探针根因修复；原失败保留。不得删除断言、把真实失败改为预期拒绝、换掉已冻结语料或拿旧run拼新源码验收。

## 工作流与验收

新工作流必须核验 `HEAD == GITHUB_SHA`、上述实现起点为祖先、SDK保护树相等、产品SQL与实现起点相等，以及 `git diff --name-only <start> HEAD` 全在本包白名单。
使用安装后C11/C++或真实原生宿主；同次报告绑定完整source/run/attempt，列逐项具名通过/失败/跳过、实际消费者SHA和明确限制。
工件名称带run/attempt，记录ID/非空字节/有效期/SHA-256并与上传日志核对。ZIP下载与实算都在Actions；严格汇总拒绝缺项、失败、跨源码/attempt、摘要错或未覆盖。
观测/审计任务将“报告已完成”和“功能/性能/无障碍通过”分开；不能用成功生成JSON授予实际能力。

## 交回与协调

推本包功能分支，给root完整受测SHA、最终文档HEAD与差异、run/attempt/job、具名结果、工件身份、原失败和未完成范围。纯证据文档提交标 `[skip ci]`。
阻塞在共享接口时，交最小复现、建议补丁及受影响公共契约；不要越权写共享文件或因等待停止所有独立工作。
root统一审查、普通merge、宿主接线及共同源码复验。六目标互通、真机、读屏、产品性能及正式发布均按实际证据分别授予。

