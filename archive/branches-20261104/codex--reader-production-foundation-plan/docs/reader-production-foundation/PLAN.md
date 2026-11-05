# 生产基础模块整合草案

状态：供 root 审阅，未推送，未启动构建、测试、语法检查或工件处理。五包既有独立云端结果保留其原 source；本草案 `accepted=false`，不能把导入后的树称为已同源验收。

## 源码取回

生产起点 **B0 = `1a6d98ed613c61ffea4267f01f83e2c49b1c02f6`**。只做指定路径快照取回，未 whole-tree merge 旧 e67。第一份 payload 是 `a19e996ed8dbab20eeb716da774f9fa286d196d8`；随后 `57f20af13364ff0bb5aa8cab6225ce1f24807def` 将 S16 的测试/工作流/审查文档替换为 root 加固后的版本。最终以 **payload P = `57f20af13364ff0bb5aa8cab6225ce1f24807def`** 为审阅锚点，不能使用第一份 payload 的旧 S16 验证器。

| 包 | 真实受测 source | 文档/快照 source | 独占模块路径 | 独占测试、文档、工作流 |
| --- | --- | --- | --- | --- |
| C06 | `909d05c31afdce27a7d8fbe861ead89f5b4552cf` | `8bf3c904862a7ff47768b7d4c707337999d5c5cd` | `apps/reader/annotation-export/`、`apps/reader/annotation-import/` | `tests/reader_next_c06/`、`docs/reader-next-c06/`、`.github/workflows/reader-next-c06.yml` |
| S14 | `c7205a9da1c11c0cc23fb04920dbd7a8071659d8` | `393399477ea68f149cfd323c6a6ce970445415ab` | `apps/reader/font-library/` | 对应 `reader_next_s14`、`reader-next-s14`、workflow，以及 `HANDOFF-RESULT-S14.md` |
| S15 | `1ca21a1a52b565c1e4de5f79a8e10921c0c77b46` | `3fc87a2aadb3425a2826ff6dc3f2a74db934045c` | `apps/reader/original-export/` | 对应 `reader_next_s15`、`reader-next-s15`、workflow，以及 `HANDOFF-RESULT-S15.md` |
| S16 | **`28df223d1df2aa3e551ad4796d5e7615bd706d8e`** | **`33beb37ddef85b12cbc9262560b952d6f004198b`** | `apps/reader/jump-history/` | 对应 `reader_next_s16`、`reader-next-s16`、workflow、handoff，包含 `ROOT-REVIEW.md` 与 `root-review-validation.json` |
| S17 | `537460e563874de1237d2e9d9bf2b0ca130c64d9` | `abd3d841bdd091ae9a98a4dddb43f7507c31e27a` | `apps/reader/sync-status-view/` | 对应 `reader_next_s17`、`reader-next-s17`、workflow，以及 `HANDOFF-RESULT-S17.md` |

表中根目录是快照选择边界，不是未来任意写入的前缀许可。精确文件集合由这些固定 Git 对象展开，最终变更集合是 `git diff --name-only B0 P`；source、文档 SHA 与根目录在 `snapshot-manifest.json` 中固定。历史 handoff 的旧失败/未授予陈述原样保留，以各 root review 记录区分后续事实。

## 依赖和 API 兼容

| 模块 | default install | 显式 raw install | 接入约束 |
| --- | --- | --- | --- |
| C06 export/import | 0.1.0，Revisions 0.3.0、ReadingState 0.1.0（import default 不依赖 decoder） | 0.2.0，Revisions 0.4.0、ReadingState 0.2.0 | importer 仍须 `READER_ANNOTATION_IMPORT_BUILD=ON`；raw 新头/新入口与旧文件格式隔离，确认指纹是完整 SHA-256 `char[65]`，不能取早期 64-bit 候选 |
| S14 font-library | package 0.1.0，SDK 默认 3.40.0 | 无 raw 族；可显式 SDK 3.41.0 | `READER_FONT_LIBRARY_BUILD=ON` 才构建；lease 借出的 `exr_font*` 不能由宿主自行 free，布局/pager 先释放再放 lease |
| S15 original-export | package 0.1.0，SDK 默认 3.40.0 | 无 raw 族；可显式 SDK 3.41.0 | include/src 与固定旧模块相同；SDK owner lease、公共 chunk source、无覆盖/清理回执契约不变 |
| S16 jump-history | package 0.1.0，ReadingState 0.1.0 | package 0.2.0，ReadingState 0.2.0 | `READER_JH_VERSION=0.1.0`、struct v1、旧函数和旧 decoder 保留；raw 固定页使用新入口，不能把 raw store 交旧函数；CMake EXACT 0.2 有意不替代 0.1 |
| S17 sync-status-view | package 0.1.0，Session 0.1.0 | package 0.2.0，Session 0.2.0 | snapshot 布局/计数/阶段保留；相同 C 入口按安装族读取 legacy/raw revisions，另一族 handle 明确失败；仍为只读 view，不 ack/retry/publish |

base 的原七个 raw 模块已经提供这些能力，五包无需修改它们。default 与 raw 必须使用分开的 configure/build/install 前缀；相同 target 名不能在同一 CMake 图里混装两族。生产 SDK 当前是 approved 3.41.0，所以构建 S14/S15 时应显式传 `EXR_SDK_VERSION=3.41.0` 与同一个 `EXR_SDK` 前缀，不能改它们保留的 3.40 默认值来自动采用新 SDK。

S14/S15 的 imported-target gate 均为同一 Git blob `98d0c8ddaf006591014203141f1faf650cc3ba4c`，source 与 installed Config 均核验实际头/归档来源，拒绝已有外来 target，不覆盖它。S14 从 `exr_core`、S15 从 `exr_library` 沿 SDK component/vendor 闭包核验。

S14、S15 与 S16 的公开 CMake target 会携带 SDK 链接闭包（S16 经 reading-state full target）。当前共享 SDK DSO 的宿主图不能仅凭静态消费者成功就直接把它们塞入 product DSO；后续接宿主时须沿既有单 SDK provider 规则做链接/符号和 owner 生命周期验收。本草案没有改任何宿主。

## 默认构建与保护边界

本次没有改顶层 CMake、presets、SDK 边界、`apps/reader/store`、原七模块、`examples` 或 `apps/reader/desktop`。只添加/升级独立 optional package 路径，未给默认 SDK/宿主增加 add_subdirectory 或默认 ON 开关。原构建入口与旧业务测试字节保持；本次没有将共同 962 分支中的实验 wrapper、Windows owner 或 Android instrumentation 复制到生产起点。

七模块指 `revisions`、`reading-state`、`reading-commands`、`annotation-view`、`commands`、`sync`、`session`。SDK 仍独立绑定 approved `edddc463c06ed5731195cdb8f06b2df6dff7699e`，旧 frozen 3.40 仍以其既有固定提交用于兼容测试。源码 Git 边界与默认配置不变不等于新组合已跑过；没有在本地执行任何验证器。

## 推荐的新 BASE 策略

1. **此刻 BASE 保持 B0。** P 只是可审阅 payload，不提升为已验收生产基线。root 可把这两份纯路径取回提交 cherry-pick 到已收口的共同运行分支，或继续在 B0 上组成新候选；都不 whole-tree merge 包的旧 e67 树。
2. root 先批准精确 payload 文件集合/各包根树，再新增独占 composition guard/workflow。guard 类型明确写为 `production-foundation`；实际 HEAD/event SHA 必须相等。SDK 对 approved SDK 校验，七模块、schema、宿主和默认配置对 B0 校验，各取回模块和原验证器对固定包 source/tree 校验。只另外授权逐个列出的 wrapper 文件，不放开任意前缀。
3. 原包的 e67 ancestry/独占路径 guard 在真实 B0 分支会拒绝；**不要先改旧 guards 或伪造它们成功**。新增的可逆投影/组合 driver 只替换声明过的 source/ownership 入口与实际 workflow 身份认证，旧测试与业务断言、限额、负例和二进制/工件绑定保留，明确记录 `legacy_guard_executed=false` 与新的 guard kind。不可 monkeypatch GitHub 返回的旧 workflow 路径、GITHUB_SHA 或旧 BASE。
4. 在同一个真实新 source 上分别安装 default/raw 两族，使用已安装 C/C++ 消费者；完整重放五包 root 修复后的业务集与拒绝集，再加组合依赖/已有 target 的边界检查。S16 必须使用 28df/33beb 的九程序、三归档、三原套身份/默认等价重算和 15 个真实变异拒绝，不退回 1f/777 的旧裁判。所有构建、语法/协议检查、夹具、下载与工件处理仍只在 Actions。
5. root 的同源 strict 真正通过后，再把该实际源码 **S** 登记为下一份、范围明确的 BASE；保留 `production_origin=B0`、各包原 source/文档 SHA、源树 hash、所有旧失败及 S 的新 run/attempt。包与 native foundation 授予不自动授予宿主 UI、移动端、六平台互通或完整产品。

## root 审阅后的下一步

优先形成 Windows/Linux 上的 default/raw 组合消费者和原完整业务集，再保持 S14/S15 已有 macOS 与 frozen SDK 兼容范围。完成组合来源验收后，宿主接入另立任务：C06 预览/确认流程、S14 字体 lease、S15 导出 owner、S16 back/forward 导航、S17 状态快照。当前没有更改任何旧 guard、没有新建或触发 CI，等待 root 决定精确 wrapper 方案。
