# Raw3 共同源码组合预检

本包起点 `e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`，只新增自身 guard、工作流与专用文档。
所有起点已有文件的 Git blob、mode 和存在性固定；包括旧裁判、旧工作流、owner、预算、生产代码。
新增文件仅限 `tests/reader_raw3_common/`、`.github/workflows/reader-raw3-common.yml` 与本包两份文档，
必须为普通 `100644 blob`，拒绝 symlink、可执行 mode、gitlink、前缀碰撞与未批准的未来 leaf 文件。

## 两种 SDK 身份

- 历史冻结 3.40：`9854061be331fe603a1822d9b2b36ee357154927`。保留其 freeze manifest 八项原树身份、ABI 1、schema 7。
- 当前批准 3.41：`edddc463c06ed5731195cdb8f06b2df6dff7699e`。当前 SDK 文件必须等于该批准树；不要求它伪装成历史 3.40。

全部原始冻结记录仍绑定自己的源码与运行。本包不继承这些运行的产品验收。

## 固定组件

`tests/reader_raw3_common/composition.json` 列出每个来源的完整 SHA 与逐项路径：raw 七包 `56793e7c`，
metadata/schema `0889f7d1`，Windows `13abefbb`，Android `caa84411`，Apple `3ee3b7de`，
WebDAV `98fa8e0f`，GTK `8cc9f4eb`。Windows 独占文件与 GTK 的共享 desktop CMake 分开 pin；
不能把整个 desktop 目录错误地归给一个平台。GTK 新 harness 需要 root 后续明确更新共同起点和 pin。

旧 guard 各有固定分支和独占路径约束，合并后的共同树会正当触发其拒绝。
本包不运行或改写它们，不重设 `GITHUB_SHA`、`GITHUB_REF_NAME` 或旧 guard 的固定来源。
它验证实际 `HEAD == GITHUB_SHA`、起点祖先及干净 checkout，再独立检查真实 Git 对象组合。

## 负例与严格汇总

全部执行只在 Actions：独立负例使用临时 index 生成实际 mutation tree，覆盖各组件 blob、旧 workflow/guard、
删除、mode、symlink、gitlink、路径、未批准未来文件、3.40/3.41 混淆和 event SHA 错配。
不修改真实 index、HEAD 或事件环境。严格作业下载本次 producer 的原 ZIP，核对来源作业、run/attempt、
SHA-256、字节、到期时间和成员；重新检查自己的同源树，并核对完整负例名单。

这是 source composition preflight。`accepted=false`、`complete_product=false`、`runtime_accepted=false`。
不同 SHA 的 Windows、Android、Apple、GTK 与 WebDAV 运行不能拼成共同产品验收。
当前尚未执行云端运行，结果见专用 [验证记录](validation/reader-raw3-common-preflight.json)。
