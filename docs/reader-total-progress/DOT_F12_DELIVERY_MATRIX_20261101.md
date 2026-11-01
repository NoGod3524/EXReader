# F12 最终交付矩阵（准备，未验收）
观察日期：2026-11-01 UTC。独立 owner：Dot F12（原 F06 验证代理）。正式 ledger 为 `5db41cb19673fb75bb0b498c677d770931ac33e8`，96/108；F12 pending，evidence=[]。此文档不改计数。

## 原条款与授权
catalog.json F12 原文：“最终版本升级/旧库兼容、许可/依赖与用户安装/导入/同步说明完备”。
用户 2026-11-01 00:32:42 UTC 明确批准第六路转 F12、独立分支两份新文档、0 生产改动、0 CI。独占分支拟为 `dot/f12-delivery-20261101`，从上述 ledger 创建；仅本矩阵及同目录 DOT_F12_VALIDATION_DESIGN_20261101.md。K03/C02 原包保留封存；其他生产 owner 不变。GitHub 直连读写授权不等于发布/签名/PR/tag 或无限 CI 授权。

## 已有固定证据及不得外推的边界
| 输入 | 固定身份 | 已证明 | F12 尚缺 |
|---|---|---|---|
| K03 Linux portable | seal `6669351b7bf44c4bdda94a70dcd2c5d7e0f50498`; source `1d30c8111e6a0ac75f3ea35ff305fbcf034477a0`; run 41176158414 A1; jobs 124464039211/124465363916 | 12/12；Ubuntu 22.04 实际 A→B 路径更新、原库/三本原件/笔记/设置/书架保留、锁拒绝第二 writer、SIGKILL 恢复、原 A 打开升级前备份 | A/B 同 SDK3.42/schema7，不是跨 schema 迁移；不含 B 修改库降级 A、硬断电、其他五端、签名/自动更新、许可/说明 |
| C02 complete | doc `721188e553be4c8cffe9fbfb204f8a544a64bfe9`; production `d32603dc65bccfd65901239d21cb65cd10bca168`; audit `5d9fc903ab015c50c3ce25b57a2680218bb0d419`; run 41194417880 A1/job124517589392 | 12 原 ZIP、105 语义负例、132 角色替换；full_c02_complete=true；迁移/持久日志/显式 Repair 及原 owner 生命周期 | 明确不授 F12/full P0；不是最终共同产品升级包；硬断电与独立 MSVC 静态重链接不在结论 |
| F06 | catalog verified；source `8f8acf3234cba747165f001c0c96efe1b911e6ad`; run 40678657371 A1；冻结 SDK `8357eafa28423a7ab93ba08b823af80f01ad1505` | 六包同源身份/安装后程序绑定限定范围 | 不是当前在途组合产品；不授六端行为、升级或最终文档完备 |
| 仓库许可资料 | ledger 的 LICENSE blob `fb13d21c0d9de00c0db1b93fe8d9330c7fba645c`; THIRD_PARTY_NOTICES.md blob `746481d9fb048d0c829dcf692e2ced5ca8eaae23` | 已存在 MIT 主许可、第三方说明及 licenses/；说明包含可选组件/字体与构建条件 | 尚未对最终每个实际程序/包的链接和分发内容建立闭合清单；存在说明不等于最终包已完整携带 |
| 产品原任务书 | docs/READER-PRODUCT-PLAN.md blob `2667f8e7c08657eeace3bb4ab406d43d81ec0bec` | 明确六目标、离线/专用 WebDAV 目录、凭据隔离及不把组件结果转授 | 不是完整面向最终用户的安装/升级/导入/同步操作说明 |

K03 原件：13032718240，449856 B，SHA256 b11adb294ec8371a3b1a3d145f2d615ef2146686a0b9ba2cd8b26228e12745c5；B 包13032907739，18573921 B，8501bb5fa5152af3ace135e354586aac484ceecc82a8d25850b82276f5b54d08；独立审计13033012644，1102 B，2de51c22912b08f44191b6c82cf2fcf7cb3378a7769eb2b725cea4e1030d39d0。
C02 原件13039319680，1055858172 B，a0dbd292b2196fa0086fe87ba08174c9df58a20c7b19a246a370521f90dcd33f。
本轮只读固定文档/源码元数据，不下载或解析 ZIP；以上原件身份来自封存记录，不能宣称本轮重散列。

## 交付缺口矩阵
| 条款 | 当前状态 | 最小下一证据 | owner / 依赖 |
|---|---|---|---|
| 最终版本身份 | 未冻结最终共同产品 SHA、各包版本及发行渠道 | 父线程确认最终候选、各平台实际包/入口/SDK/协议/schema 身份 | 主集成负责人；F12 不自行选择最新 SHA |
| 升级与旧库兼容 | K03 仅 Linux 同 schema 路径更新；C02 仅限定迁移能力 | 支持的旧版本→最终版本清单；逐平台真实旧 profile 升级、原件/记录/设置/离线状态、失败保留；仅承诺的迁移范围 | 各 host owner 提供真实程序/行为；F12 汇总 |
| 备份/恢复/不支持路径 | 旧库降级、硬断电不能冒称通过 | 用户说明明确备份恢复与不支持降级；若正式承诺新增迁移，先设计/授权 | C02/K03 封存只读，不夺 writer |
| 许可/依赖 | 仓库已有材料，最终包对账未做 | 每包实际依赖/版本/构建选项/分发字体、许可原文及 notices 随包位置；缺项精确列出 | F12 证据整合；需要生产/打包修复再授权原 owner |
| 安装说明 | 六目标最终安装入口与限制未绑定 | 与实际包一致的支持系统/架构、安装/启动/更新/用户数据位置及卸载数据边界 | F11 真机/架构未测范围明确，不以模拟器替代 |
| 导入说明 | 有模块/host 证据，未形成最终操作说明闭环 | 支持格式与入口、重复/取消/失败、系统文件授权、本地下载与删除区别 | UI/host owner；F12 不改 UI |
| 同步说明 | F03/F04/F05/F07/F10 在途，不能写成全绿 | 实际账号/专用目录/TLS/凭据、离线与重试、冲突/墓碑、手动操作、现有限制对应同源结果 | 各 F owner；不读真实凭据、不连接用户云盘 |
| 最终验收 | F12 pending | 上述每项证据完整、独立复核、精确未覆盖说明后才提总表验收 | 父线程总验收；本轮计分0 |

## 交接与下一步
1. 不等全部生产闭环即可整理已有说明/许可的来源与缺口，但不得虚构最终运行结果。
2. 下一新测试/工具实现先交验证设计、独立审查，再申请精确路径与单轮 CI cap；合入参数化 suite，不另增永久重复 workflow。
3. 当前无新 CI，未运行构建/语法/测试；两文档完成不等于 F12 完成。工期因最终候选和平台证据未冻结无法可靠估算。
4. F09/UI/F08 及其他未明确转交 owner 保留；F03 Apple 两文件和 F10 cleanup/managed 的新授权不转授 F12。

## 固定入口
- [K03 seal](https://github.com/NoGod3524/EXReader/blob/6669351b7bf44c4bdda94a70dcd2c5d7e0f50498/docs/reader-total-progress/K03_LINUX_PORTABLE_UPGRADE_20261031.md)
- [C02 seal](https://github.com/NoGod3524/EXReader/blob/721188e553be4c8cffe9fbfb204f8a544a64bfe9/docs/reader-total-progress/DOT_C02_NATIVE_JOURNAL_CANDIDATE_20261030.md)
- [F06 ledger](https://github.com/NoGod3524/EXReader/blob/5db41cb19673fb75bb0b498c677d770931ac33e8/docs/reader-total-progress/f06-sdk342-six-packages.md)

## 已有许可严格门禁复用（00:36 UTC 只读补证）
ledger 中 docs/READING-LICENSES.md（blob 54b08a36854a785ee035ccddab20464cf3aee68c）及 docs/READING-LICENSE-REVIEW.md（blob c5b1a65f91a2ee4a921556d9b814f9c5be320a52）已有 H5 严格出口。修补 source 72c1e89659679b7d7b76504007a84d6d8c453db3 / run39862694733 A1，以及记录的共同 SDK 复验 run39871878859，保留 31 拒绝、1 必需材料缺口阻断、3 正控；材料库存绿色与 release_ready 严格条件分离。其范围仅 Linux 两 reading presets 静态 SDK，不含 Windows/macOS/Android 宿主、宿主字体和音频构建。
后续应复用 tools/check_reading_licenses.py 的既有材料/来源/固定版本/构建开关/安装归档方法和原断言，不从头另造扫描系统；当前最终六个应用包仍需实际分发内容对账，不能借 H5 转授。
docs/READING-RELEASE-PLAN.md 的“六包”是 reading-core/library × Linux/Windows/macOS 的 SDK 六包，不是 Windows/macOS/Linux/Android/iPhone/iPad 六应用；其默认分支祖先和发布准备要求不能自动改写成本任务允许发布。

## 宿主打包路径只读盘点（共同准备源94fb，非最终验收）
- `tools/build_linux_host.py`：复制根 LICENSE、THIRD_PARTY_NOTICES.md、SDK share/exreader/licenses、Reader.otf 与 OFL.txt。
- `tools/build_windows_host.py`：对应 LICENSE.txt、THIRD_PARTY_NOTICES.md、licenses/、Reader.otf 与 OFL.txt。
- `tools/build_apple_host.py`：app resources 中复制 EXReader-LICENSE.txt、THIRD_PARTY_NOTICES.md、SDK licenses/ 与 Noto-OFL.txt。
- `tools/build_android_host.py`：已见 Reader.otf/OFL.txt 和 catalog assets；当前所读 Gradle 配方未见根 notices/SDK licenses 拷贝。只标“APK 内材料待原件核证”，不据局部源码断言整个外包缺材料。
以上是源码规则，不是本轮 ZIP 实物检查；SDK notices 存在不证明所有宿主 WebDAV/系统依赖或最终构建开关已经闭合对账。
F06 已核开发包形态：Windows/Linux 开发ZIP、macOS ad-hoc开发app、Android API34 x86_64 emulator/debug APK、iPhone/iPad arm64 simulator app。安装说明必须保留这些限制，不称正式签名真机交付。

下一设计审请求：可先审 F06 固定六原 ZIP 的历史材料缺口，复用既有身份和原材料门禁，仅 Actions 读取、不重建；该结果只能授历史包盘点，不授尚未冻结的最终 F12。当前尚未批准测试文件/CI，未执行。
