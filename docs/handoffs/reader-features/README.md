# 阅读器独立功能交接

五包从同一固定起点各自新建分支、独立工作树，交给五个外部智能体即可并行。
共同实现起点：`c3511a011eefbf1fba1d20908f000cef22b1ced2`，来自
`codex/reader-reading-v2`。不要跟随该分支之后的移动HEAD。

该起点包含已验收的侧载、产品目录/修订、reading-anchor v2、按书标注分页及原件导出。
原件导出与保留阅读套件的受测源码为`745c348380e3e2270ded933fe3252a7d364bf95b`，
run`40059480968`同源五作业成功；具体范围见`docs/READER-SOURCE-EXPORT.md`。
这些记录是依赖基线，不授予下面新包验收。

| 包 | 分支 | 任务文件 |
| --- | --- | --- |
| F1 书内搜索 | `codex/reader-search` | [search.md](search.md) |
| F2 目录导航 | `codex/reader-navigation` | [navigation.md](navigation.md) |
| F3 阅读设置 | `codex/reader-preferences` | [preferences.md](preferences.md) |
| F4 文件夹批量导入 | `codex/reader-batch-import` | [batch-import.md](batch-import.md) |
| F5 真实文档验收 | `codex/reader-real-corpus` | [real-corpus.md](real-corpus.md) |

优先F1/F2/F3。五包没有相互依赖；公共接口只消费上述固定起点。
root继续负责账号/凭据/同步、下载导入与投影调度、四套宿主接线、共同源码最终验收。
当前Apple书架、Android整理和凭据复核各有owner；不得修改其分支和文件。

## 全包共同约束

- SDK固定K=`9854061be331fe603a1822d9b2b36ee357154927`，SDK3.40.0、ABI1。
  `src/`、`include/`、`cmake/`、顶层`CMakeLists.txt`、`tests/fixtures/`、`bindings/`、
  `.github/workflows/native.yml`、`.github/workflows/reliability.yml`逐字保持。
- 产品schema1、既有wire v1与reading anchor v1/v2、原预算和原门禁不改。
  不读SDK私有SQL，不增加新同步实体，不把本机SDK行号当跨设备身份。
- 只修改本任务列出的新增路径；不改宿主、root公共模块、其他任务或现有工作流。
  不更新这六份handoff。确需共享修改时交最小复现及补丁建议，由root实施。
- 模块使用安装后的公开组件，独立CMake及C ABI，默认reading构建不加入。
  所有权、回调寿命、取消、错误及输出清理规则在公开头中写清；接口本身不创建后台线程。
  不引入WebView、JavaScript UI、新服务端、新通用框架或额外密码学实现。
- 本地只读写源码/文档和Git；构建、测试、语法检查、夹具生成、benchmark、
  工件下载/解析全在GitHub Actions。本地不执行Python语法检查。
- 新工作流固定受测source，检查共同起点祖先、SDK保护树和产品schema未变、包路径归属。
  同次报告必须绑定完整source/run/attempt，列具名检查与通过/失败/跳过，原失败保留。
  同次工件ID/字节/SHA-256/有效期与上传日志核对；缺证据不算通过。
- 不改默认分支/保护规则、不合并PR、不建tag/Release、不接入真实账号或用户私有文档。
  不重启仍在运行的CI；观察超时先复查原run。不要因尝试通过而减掉既有检查。

## 交回root

推自己的功能分支；给出受测完整SHA、最终文档HEAD及两者差异，固定run/attempt/job、
逐项结果、安装后消费者、工件ID/字节/SHA-256/有效期、原失败和明确剩余范围。
源码之后的纯证据/文档提交标记`[skip ci]`。不替root合入；不借旧源码通过项拼验收。
模块通过只授予本包接口；宿主UI、产品性能和六平台互通由root另行联合验证。
