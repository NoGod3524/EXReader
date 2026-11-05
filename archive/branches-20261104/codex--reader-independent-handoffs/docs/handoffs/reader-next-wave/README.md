# 接续独立工作包：共同约束

用户于2026-10-24改为“每交回一次，就可以准备重新拆包”，本批由用户**手动 handoff**。这些文档是可执行交接，不表示已派发或实现。各包均从固定源码 **f43baf9182d75907c0cb5d6f77048f27bca8c950** 独立开始，不跟移动 HEAD，不等待其它 J 包，不修改其它 owner 的宿主文件。

## 开工与唯一写入者

- 仓库：https://github.com/NoGod3524/EXReader 。先读本页及自己的任务页；在独立 worktree/clone 从上述完整 SHA 新建任务页指定分支。禁止切换或重置用户现有工作树，禁止修改其它工作树。
- 若任务分支已存在，先核查作者、工作区、运行及 owner，交 root 协调，不能重置或双写。用户手动分发；本包可提交并推送自己的功能分支、触发并修复Actions，不需停在“要不要push”。不创建/合并PR，不推默认分支。
- 当前 Windows、GTK、Android、Apple 生产宿主由root和三个主线owner独占。本批通过新的组件/probe接入范例实现；产品接线由root后续统一做，不能借此把包本身写成空壳。

## 不变项

1. SDK固定 `9854061be331fe603a1822d9b2b36ee357154927`，SDK3.40.0/ABI1。保护路径 `src/`、`include/`、`cmake/`、顶层 `CMakeLists.txt`、`tests/fixtures/`、`bindings/`、`.github/workflows/native.yml`、`.github/workflows/reliability.yml` 逐字不改。
2. 产品schema1、既有wire v1和reading anchor v1/v2不改；不新增同步实体。不读SDK私有SQL，不用本机SDK行号作跨设备身份。新本机私有sidecar若确需使用，必须独立版本化、限额并记录原子性，不能冒充产品事务。
3. **所有构建、测试、语法检查、夹具生成、benchmark、服务、工件下载/解包/解析仅在GitHub Actions。** 本地仅源码/文档/Git；不得运行Python parse、编译器、测试或下载旧ZIP分析。
4. 无WebView/JS UI，无新常驻服务器、插件框架或重复解析器；优先复用安装后的公共包。C/C++库公开C ABI并独立CMake安装；平台组件使用原生API和独立probe，默认reading配置不自动加入。
5. 现有限额/CPU基线/数值预算不放宽。新限额在代码/文档明确，测试预期在消费者读夹具前固定。报告完成、模块功能、宿主功能、性能、无障碍、真机分别授予。
6. 不用真实账号秘密、私人文档或用户云盘；测试CA仅在Actions临时runner/模拟器。禁止正式签名发布、tag/Release、改保护规则或原六SDK发布包。

## 每包相同的云端出口

- 每作业守卫：`HEAD == GITHUB_SHA`、固定起点为祖先、SDK保护树相等、产品SQL与起点相等，`git diff --name-only <start> HEAD` 全在该包白名单。不得改白名单绕过越权。
- 从安装前缀编译实际C与C++消费者（平台library用真实独立app/probe）；验证所有权、错线程/重入、取消、输出寿命、边界和有意义的故障路径。适用平台逐个真实执行；不能用单纯grep、mock或空main授予实际行为。
- source/run/attempt/平台/消费者及安装包SHA绑定；逐项具名pass/fail/skip/pending，不只打印总数。严格汇总核上游作业和同次工件名称、ID、字节、digest、有效期，Actions内下载并重算ZIP摘要和报告身份，拒绝缺项/跨源码/跨attempt/篡改。
- 原失败与工件保留，不删除断言、换语料、把真实失败改预期拒绝或用旧绿拼新源码。发现共享实现缺陷，交root最小复现及建议补丁，不越权修改。
- 文档交付包括契约、复现、限制、原失败；验收JSON初始accepted=false，真实跑过后按范围填写。证据文档提交标`[skip ci]`，明确tested source和最终HEAD差异；有源/测试差异不能称纯文档HEAD。

## 交回

给root：完整受测SHA、最终HEAD/差异、分支、run/attempt/job、具名结果、工件ID/非空字节/sha256/有效期、实际消费者SHA、失败原件与未覆盖范围。root复核、按依赖接入和共同源码复验后才计集成完成。每五个**已完成集成轮次**仍由root审计；提前准备下一包不增加完成轮数。

