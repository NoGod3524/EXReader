# 阅读核心：H5–H11 外部交接

本索引及各包是给独立 AI 的执行指令。H3/H4 不在此重复。
目标：原生多格式解析和自有 PDF 渲染、轻量化、可量测性能；不依赖 WebView。

| 包 | 交接文件 | 当前可执行范围 | 依赖 |
| --- | --- | --- | --- |
| H5 依赖与许可证 | [H5](reading-H5-licenses.md) | 可立即执行 | 固定 reading preset 候选 |
| H6 平台证据门禁 | [H6](reading-H6-platform-gate.md) | 可立即执行 | H1 固定交付 |
| H7 文档事实校正 | [H7](reading-H7-doc-state.md) | 可立即执行 | H1/H2/R3 已有交付 |
| H8 Windows 有界阅读 | [H8](reading-H8-windows-bounded.md) | 先准备；SDK 冻结后首个完整 pilot | 随机读、导入、进度及标注契约 |
| H9 Apple 有界阅读 | [H9](reading-H9-apple-bounded.md) | 先准备；冻结 SDK 并完成 Windows pilot 后接入 | 同 H8 |
| H10 Android 有界阅读 | [H10](reading-H10-android-bounded.md) | 先准备；冻结 SDK 并完成 Windows pilot 后接入 | 同 H8 |
| H11 Linux 有界阅读 | [H11](reading-H11-linux-bounded.md) | 先准备；冻结 SDK 并完成 Windows pilot 后接入 | 同 H8 |

H5/H6/H7 可相互并行。平台准备可并行，正式实现使用同一个明确的 SDK 冻结提交，
不要各自实现新的数据库或位置协议。主代理负责 SDK、性能热点决策与最终集成。

## 全部包共同约束

1. 本地只读写源码/文档和执行 Git。编译、测试、语法解析、语料生成、benchmark、模拟器、
   工件解析和汇总全部在 GitHub Actions 执行；不下载工件，不开本地服务或常驻监测。
2. 从各包指定完整 SHA 创建自己的工作树和分支。首先核对远端 SHA、祖先与文件差异；
   不重置别人的工作树，不推 `codex/framework` 或 `codex/r1-reading-core`，不合并 PR。
   允许推自己的分支并启动本包云端工作流。
3. 只改本包拥有的路径。共享 SDK、preset、现有验收断言有问题时交给主代理，
   不复制替代实现、不降级断言、不静默跳过、不增加 WebView。
4. 失败保留。交付完整受测 SHA、run/attempt/job、逐项结果、工件 id/大小/digest/到期时间、
   后续纯文档 HEAD 和精确限制；工件必须绑定同次源码。旧通过项不能拼入新候选。
5. 以最少变更完成出口。没有性能预算时报告测量，不能自行宣布达标；
   合成 smoke 不算真实语料，历史真实语料仍为 0/1710。
6. 工作完成后输出可合入提交与差异路径。遇到依赖缺失，交付准备成果与准确阻塞点，
   等待固定接口，不能把设计草案当现有 API。

## 已固定输入

- 阅读主线基准 B：`b529513b7e8e8992786f8c679c0ec6c92110b035`。
- 联合验收 S：`686ce2fe6c3463ef1b917569677ee9933e22faa9`，只覆盖已声明包范围。
- H1 实现：`9b968a16fc47596725e849e56ee98e4c4c210b74`；文档 HEAD：
  `2e8e981b6dd44d855a23931480fe5e0d5c791762`；run `39854485070`，4/4 成功。
- H2 HEAD：`2e3e2f1764e0f605122ec4cbced1e05deb96a9e8`，父提交 B。
- R3 初始 PDF 测量：实现 `3cd7bdf14d4ee961a9cdda98bd7410d34c04161b`，
  文档 HEAD `49827eeab34d7faf868d2dc975cfd926a67d1f23`，run `39855093753`。
  新增可区分多页源码 `4b6f562c29181d509f470feda0e5f1226fd466bb` / run `39856195765`
  已由 R3 子代理交付成功记录：12 进程/240 次绘制、60 项拒绝自验；文档 HEAD
  `ea3d4d1a24c0febd8d14f110594b7226e2527c82`。执行时只读复核云端记录。
- R5 在 `codex/r5-library-source` 开发中，尚未冻结；新增随机读出口本身不等于导入、章内持久化已完成。

## 平台包统一开工信号

主代理交付一份固定源码/云端验收记录，列明原件 source、EPUB 有界导入、稳定 part+path、
章内进度与标注、旧数据处理、取消与所有权。H8 首先完成书架闭环；
后续三平台使用同一契约。接收此前可阅读源码、列接入点和准备测试计划，但不推测接口实现。

参照 [宿主接入地图](../R5-NATIVE-HOST-ADOPTION.md)。
