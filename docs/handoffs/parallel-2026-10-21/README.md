# EXReader 第二批独立子包分派

本批从已验收功能继续补宿主、迁移与服务入口。五个外派包可分别交给五个智能体；四个内部子包由主代理协调 subagent。

## 基线与执行约定

- 实现基线：`a2552d7feb786cd2345d2b0b3eb894777b3254db`，SDK3.40.0、核心3.39.0、ABI1、书库schema6。
- 当前云端长测固定源码：`635225fe6ceb7759a948a1d8cede0ab18ea1cee9`，run `39666440519`。不得取消、重启、修改预算或把新分支算入该批通过结果。
- 外派分支从本批handoff提交建立，包含全部说明；各自建立独立工作树，不修改用户共享主目录或他人工作树。
- 用户授权本包实现、独立分支提交/推送与GitHub云端CI；不自动合并、不改发行版本、不请求真机签名/安装。
- **构建、测试、模拟器、OCR、语料生成、基准全部只在GitHub云端执行。** 本地仅允许源码/文档检查、编辑和Git操作，不启动本地测试、常驻轮询或证据下载/重汇总。
- 复用公开SDK。不得直接依赖`src/internal.h`、私有结构或SQLite内部表；不得修改`src/`、`include/`、`cmake/`、顶层`CMakeLists.txt`及既有`native.yml`/`reliability.yml`。
- 缺少必要公共能力时，完成不依赖该能力的工作，并在本包文档列出具体接口需求；不绕过所有权、资源上限或取消约定。
- 专用workflow由各包拥有，建议`push`仅触发本包分支及本包路径，另允许`workflow_dispatch`；不定时触发，不重复启动96分片长测。既有`native.yml`默认仅在主线push/PR或手动触发，不能把分支push当作已跑完整CI。
- 构建消费使用安装后的SDK及精确版本；可先在云端从本分支安装SDK。组件被关闭时，明确依赖或正确裁剪，不伪称所有配置均可用。
- 全局`HANDOFF.md`、`SUPPORT_MATRIX.md`、`RELIABILITY-HANDOFF.md`、版本及集成工作流由集成人统一维护；各包只更新自己文档和证据，提交需要集成的建议清单。
- 原失败、夹具、预算、容差及历史证据全部保留。报告只引用文件路径，不贴崩溃栈、fuzz样本或攻击性描述。

## 分派与文件归属

| 编号 | 负责人 | 分支 | 专属范围 |
| --- | --- | --- | --- |
| E1 | 外派智能体1 | `codex/wp12-legacy-migration` | `extras/migration/`、`tests/migration/`、迁移专用工具/工作流/证据 |
| E2 | 外派智能体2 | `codex/wp15-opds` | `extras/opds/`、`tests/opds/`、OPDS专用工具/工作流/证据 |
| E3 | 外派智能体3 | `codex/wp13-windows` | `examples/reader.c`、`examples/windows/`、Windows宿主工具/专用工作流/证据 |
| E4 | 外派智能体4 | `codex/wp13-apple` | `examples/apple/`、Apple宿主工具/专用工作流/证据 |
| E5 | 外派智能体5 | `codex/wp13-android` | `examples/android/`、Android宿主工具/专用工作流/证据 |
| I1 | 内部subagent | `codex/wp13-linux-host` | `examples/linux/`、Linux宿主专用工具/工作流/证据 |
| I2 | 内部subagent | `codex/wp11-ocr-adapter` | `extras/ocr/`、OCR专用工具/工作流/证据 |
| I3 | 内部subagent | `codex/wp16-doc-audit` | 当前矩阵与历史文档口径审计；不改引擎和原验收JSON |
| I4 | 内部subagent，排队 | `codex/compat-corpus-manifest` | 独立语料预期/来源清单和云端验证，不覆盖原语料驱动或旧结果 |

`examples/CMakeLists.txt`、共享Swift/JNI适配及`tools/host_font.py`先保持只读；新宿主功能优先使用app内局部桥接。Windows需要调整既有example构建时，先提供小补丁，由集成人应用。其他包用自身目录内的独立consumer构建，不能多人同时改共享入口。

## 五份外派handoff

1. [E1 旧数据迁移](E1-LEGACY-MIGRATION.md)
2. [E2 OPDS](E2-OPDS.md)
3. [E3 Windows宿主](E3-WINDOWS-HOST.md)
4. [E4 Apple宿主](E4-APPLE-HOST.md)
5. [E5 Android宿主](E5-ANDROID-HOST.md)

每份handoff均可独立启动；启动前同时读取本页。五包互不等待另一包完成，不接入对方尚未发布的接口。后续共同集成迁移、OPDS、OCR和TTS到各宿主另做联合验收。

## 通用交付与拒绝条件

交付实际实现、独立消费示例、专用云端工作流、包内说明与证据JSON。报告包含分支、HEAD与实现提交、workflow/run/job、SDK/程序/字体/输入身份、平台、逐case结果、预期/实际/通过/失败/未完成数及未满足项。

人工步骤必须区分已实际执行、自动化执行与未执行；模拟器不能替代真机，编译/静态检查不能替代交互。专用workflow应在失败时也上传已有日志、报告和截图，避免覆盖旧证据目录。

任何必做case缺失、跳过、失败、取消、仅编译、无真实数据通路、证据不匹配、依赖本包未声明的接口，均不得宣布本包完成。修复后使用新证据目录，保留原失败。无需为常规可逆实现选择再次向用户确认。

本包完成不代表整个WP12/WP13/WP15或产品已完成；按照各自明确的子包范围验收。待五份外派交付后，集成人统一核对公共契约、联合运行、文档、版本及新的源码验收范围。
