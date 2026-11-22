# 阅读器开发包：安装、升级、导入和同步

当前可用的是开发/测试包。下载时核对源码 SHA、SDK 版本、操作系统、CPU 架构和包内 manifest；
SDK 头文件/静态库用于开发，安装阅读器需要包含宿主可执行程序的包。
本轮能力与未测列表见 [D-FINAL-C 审计](reader-total-progress/dfinal-c-audit-20261114.md)；[前轮记录](reader-total-progress/dfinal-c-audit.md)保留原始范围。

## 安装与首次打开

| 系统 | 当前入口 | 安装步骤与产物边界 |
|---|---|---|
| Windows | 含 `EXReader.exe` 的开发 ZIP | 完整解压到可写目录，保留同包 DLL/资源后启动；选择本地书库。不要只拷贝 EXE。 |
| Linux | GTK 开发包 | 按该包列出的 GTK/系统库依赖安装，解压后运行宿主；无显示环境只能测模型。 |
| macOS | 开发 `.app` | 保留完整 app bundle；开发签名和正式签名/公证分别核对包说明。正式公证发布未在本轮验证。 |
| Android | 历史 x86_64 debug APK；本轮 arm64 基础 debug APK | x86_64 包用于对应模拟器；本轮 [Actions43667039578](https://github.com/NoGod3524/EXReader/actions/runs/43667039578/artifacts/14143305427) 含 `mobile-host/host-debug-arm64-v8a.apk`，可用 `adb install -r host-debug-arm64-v8a.apk` 安装到匹配设备，实际设备安装尚未验证。该基础包关闭可选同步/阅读记录/wave3集成，不能作为完整产品使用。 |
| iPhone/iPad | arm64 simulator app；device SDK | simulator app 只能由对应 Xcode Simulator 安装；普通设备需要 owner 的 Apple 签名身份、provisioning 及已签宿主包。本轮 device 静态库与 unsigned IPA 不提供普通真机安装能力。 |

Apple 开发宿主构建入口为 `tools/build_apple_host.py`，Android 为 `tools/build_android_host.py`；
它们是开发/CI 工具，所需 SDK 和可选产品模块须是匹配版本，不能拿历史 SDK 包与新宿主随意拼接。
本轮 arm64 APK 的 SHA-256 为 `90f93eba01cddf00f72a633d2e1c872f8e6a3b2c24c7d19114f36f2a62cb5cdf`；
debug certificate SHA-256 为 `d28e33bf727af4f0d11f273e75413ce13a15acbd2df27e91e9b6375bdce9e1e6`。
覆盖更新需与旧包签名一致；若不一致，保留原数据和旧包，停止覆盖更新，不以卸载绕过升级检查。

## 升级与备份

1. 记录旧宿主/SDK 版本及书库位置，关闭所有使用该书库的进程，再备份完整应用数据目录和原书。
   产品 `reader-catalog.db`、SDK 库、同步修订/outbox 及设置一起保留；不要复制正在写入的 SQLite 文件。
2. 保留旧程序和备份副本，在副本上用新程序打开；SDK schema1–6 支持迁移到7，本轮测试只证明这些独立布局的数据保留与复开。
3. 核对书数、原件可读、标题/作者/分类、笔记、进度和待同步状态；失败时保留日志和副本，退出新程序后恢复整套旧备份与旧程序。
4. 迁移后的库不要交给旧程序直接使用。未知 schema/其他应用数据库应拒绝；不要改 `user_version` 强行打开。
5. 宿主 parser 标签与 SDK schema 是两件事。3.40→3.41 的 macOS owner 历史证据不能证明最终六端兼容；
   当前最终包的产品数据、账号/凭据迁移及中断恢复仍待平台实测。

产品目录库单独使用 schema1→2→3 的逐段事务升级，和 SDK schema7 独立。
某一段失败时会回滚该段，先前完成的段可以保留：例如从1升级时，第二段失败可能留下完整的2。
不要手工删除迁移冲突表或修改版本号；保留失败副本及日志，由修复后的程序重新打开副本，
核对原件状态、分类、原修订和 outbox 重试计数后再决定替换正式库。
当前自动测试用历史 SQL 布局和注入的事务失败验证保留/重试，实际旧宿主升级与断电恢复另需平台证据。

系统安全存储的凭据不在书库备份里。保留原应用身份及平台账号访问，升级后先检查账号连接；
需要重新认证时在宿主账号入口输入，不把 Keychain、Credential Manager 或 Keystore 的内容写入迁移包。

旧 Web/IndexedDB 数据使用 [旧版迁移工具及包格式](WP12-LEGACY-MIGRATION.md) 导出迁移包后导入，
不要把浏览器数据库文件改名为原生书库。原始导出包与旧库备份保留到新端核查完成。

## 导入原书与标注

- 从宿主“导入”入口选择本地文件。移动端使用系统文件选择器授予访问；有线传输使用 Android 文件传输、Apple 文件共享。
  完成前保持源文件可读，不移动或修改它。重复原书按格式+原始字节识别，不以文件名作为身份。
- EPUB/CBZ 支持随机读来源；PDF 使用宿主稳定私有文件；其他重排格式首版最多32 MiB。
  取消或格式拒绝后检查原有书籍仍可打开；不要把导入失败当作成功入库。
- 开启 raw3 功能的 Apple 宿主从标注功能选择 JSONL，先预览目标书、数量、未定位/NULL/缺父版本情况，再确认。
  确认绑定完整文件摘要，预览后换文件须重新预览。取消后已提交项可能保留，重试同一文件会识别重复。
- JSONL 是机器交换格式；Markdown 是阅读用导出，不能作为标注导入。
  raw3 与旧 v1 文件互拒，未知版本、错误书籍身份或 hash、超限/未定位均拒绝，不手工删字段绕过检查。
  导出只携带 heads，不能恢复未包含的祖先历史；NULL 选择器保留原值，不能导航。
- iPad 实际文件选择、保存、预览/确认和错误 UI **需真机**；本轮 Windows/Linux 模型结果不证明这些交互已通过。

## WebDAV 同步

在提供同步功能的匹配宿主中配置同一个 HTTPS WebDAV 账号和专用目录；先导入一小本书并同步，
再在第二设备接收并核对原件、进度、标注和分类。不要把应用正在使用的 SQLite 数据库放进云盘同步目录。
同步对象是不可变原书、产品实体修订、离线 outbox 和墓碑。

断网时保留本地原书和待同步状态；恢复连接后检查账号错误详情再显式重试。401 时更新凭据。
凭据使用平台安全存储，不可用时仅保留会话；不要把密码写入日志或导出文件。
远端位置只有公开 resolve 得到 FOUND 才可导航；当前阅读不会被远端进度自动强制跳转。
并发修改保留多个版本，删除保留墓碑；“移除本机下载”和“从书库删除”是不同操作。
六端最终包及真实两设备闭环仍缺共同源码实测，不能把模块 HTTPS 通过当成宿主全流程通过。

## 随包依赖与许可材料

第一方采用 [MIT](../LICENSE)。阅读 SDK 的固定依赖、版本、来源归档 SHA-256 和开关以
[cmake/deps.cmake](../cmake/deps.cmake)、[第三方 notices](../THIRD_PARTY_NOTICES.md)
与 [机器检查清单](../tools/check_reading_licenses.py) 为准，发行者需随实际启用组件交付
`share/exreader/licenses/`、LICENSE、THIRD_PARTY_NOTICES 和依赖清单。

阅读配置包含 FreeType、Expat、miniz、stb，书库配置包含 SQLite；WebP、TIFF/zlib、AVIF/libaom、
OpenJPEG、LittleCMS、Mbed TLS 随功能开关启用。音频独立，MP3/minimp3 与 AAC/FAAD2 不属于默认 reading preset；
FAAD2 的 GPL 许可开关需按实际构建记录，不能沿用纯 MIT 说明。宿主字体、平台库和可选同步/产品模块另列。

已有 [分发依赖/SBOM 库存](READER-DISTRIBUTION-INVENTORY.md)、[阅读许可材料检查](READING-LICENSES.md)、
CycloneDX 1.5 SBOM（`docs/sbom.cdx.json`）与 SPDX 2.3 SBOM（`docs/sbom.spdx.json`）。
SDK 安装包（`share/exreader/`；`docs/` 另含许可审查文档）与 Windows/Linux 宿主分发包（`tools/build_windows_host.py`、`tools/check_windows_host.py`、`tools/build_linux_host.py`）均随包打入本说明文档（`READER-INSTALL-UPGRADE-IMPORT-SYNC.md`）、`LICENSE`（Windows 包为 `LICENSE.txt`）、`THIRD_PARTY_NOTICES.md`、`licenses/`（含 `hyph-en-us.LICENSE.txt`）、宿主字体 `Reader.otf`/`OFL.txt` 以及 `sbom.cdx.json`/`sbom.spdx.json`，由 `tools/check_f12_distribution.py` 自动核查文件存在性与组件数（43 个 CycloneDX 组件 / 44 个 SPDX 包）。非 Windows 真机四端及旧宿主真实数据/账号凭据升级中断恢复按 2026-11-15 scope 排除。
