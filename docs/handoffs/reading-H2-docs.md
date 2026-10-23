# H2：项目与阅读构建文档同步

## 目标与输入

给独立 AI 的文档小包：把既有新定位文档与阅读 preset 的真实状态同步成一致入口。
按 [交接索引](reading-simple-index.md) 从主线最新固定 SHA 建自己的分支/工作树。
文档分支 `codex/project-description` 的 `8c25d2f` 含项目收敛与 A/B/C 最终登记，
只读取相关文档差异；不要直接 merge 该分支，把其他实现历史带入主线。

新定位：多格式解析、自有 PDF 渲染、纯原生、轻量、高性能；不依赖 WebView；
MuPDF 等用于对照，不再要求全面超越。已有可选能力保留，新增扩展按需求推进。

## 文件边界与执行

仅编辑 `README.md`、`docs/PROJECT_OVERVIEW.md`、`docs/COMPETITIVE.md`、`docs/VERSIONING.md`、
`docs/ARCHITECTURE.md`、`docs/PROJECT_STUDY.md`、`docs/WORK-QUEUE-2026-10-22.md`、`docs/CORE-ROADMAP.md`。
需要引用交接记录时用既有固定提交 GitHub 链接，不随手复制原始工件。
不改构建、测试、工具、工作流或 SDK 版本字段。

1. 比较当前文件与文档分支内容，按最终定位同步；旧 JavaScript/WebView 方案明确标为历史。
2. 写清 `cmake --preset reading-core`、`cmake --build --preset reading-core`、
   `cmake --install build/reading-core`，及 `reading-library` 的用途、Ninja/编译器前置条件。
3. 标明关闭音频/索引/PDF 编辑等，不声称 PDF/图像能力因裁剪增强或性能已经达标。
4. 用 GitHub 只读信息核对最新云端结果。完成、运行中、未执行分开；
   初始 1 MiB TXT 采样不替代 PDF、随机跳页、真实语料或硬预算。
5. A/B/C 的 S=`686ce2fe`、12组35作业及严格汇总通过记录保留，旧长测只绑定原源码。
6. About 当前 GPLv3 与 MIT 主许可不一致：提供建议文案，说明可选 FAAD2 组合产物的 GPL 义务；
   本包不修改仓库设置、About、许可证原文、版本或 tag。

交付文档 diff、链接核对结果、仍待决定的信息和固定提交。纯文档不跑构建或另造测试；
只需 Git 差异与链接核对。本地不运行任何编译、测试、生成器、benchmark 或工件解析；
不推默认分支、不合并 PR，不启动代理或常驻监测。
