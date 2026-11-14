# 阅读器开发包：安装、升级、导入和同步

当前可用的是开发/测试包。下载时核对源码 SHA、SDK 版本、操作系统、CPU 架构和包内 manifest；
SDK 头文件/静态库用于开发，安装阅读器需要包含宿主可执行程序的包。
本轮能力与未测列表见 [D-FINAL-C 审计](reader-total-progress/dfinal-c-audit.md)。

## 安装与首次打开

| 系统 | 当前入口 | 安装步骤与产物边界 |
|---|---|---|
| Windows | 含 `EXReader.exe` 的开发 ZIP | 完整解压到可写目录，保留同包 DLL/资源后启动；选择本地书库。不要只拷贝 EXE。 |
| Linux | GTK 开发包 | 按该包列出的 GTK/系统库依赖安装，解压后运行宿主；无显示环境只能测模型。 |
| macOS | 开发 `.app` | 保留完整 app bundle；开发签名和正式签名/公证分别核对包说明。正式公证发布未在本轮验证。 |
| Android | 历史 x86_64 debug APK | 适用于对应模拟器；开发者可用 `adb install -r app-debug.apk`。arm64 SDK 构建产物不能安装，尚缺 arm64 宿主 APK 和真机结果。 |
| iPhone/iPad | arm64 simulator app；device SDK | simulator app 只能由对应 Xcode Simulator 安装；普通设备需要 owner 的 Apple 签名身份、provisioning 及已签宿主包。本轮 device 静态库与 unsigned IPA 不提供普通真机安装能力。 |

Apple 开发宿主构建入口为 `tools/build_apple_host.py`，Android 为 `tools/build_android_host.py`；
它们是开发/CI 工具，所需 SDK 和可选产品模块须是匹配版本，不能拿历史 SDK 包与新宿主随意拼接。

## 升级与备份

1. 记录旧宿主/SDK 版本及书库位置，关闭所有使用该书库的进程，再备份完整应用数据目录和原书。
   产品 `reader-catalog.db`、SDK 库、同步修订/outbox 及设置一起保留；不要复制正在写入的 SQLite 文件。
2. 保留旧程序和备份副本，在副本上用新程序打开；SDK schema1–6 支持迁移到7，本轮测试只证明这些独立布局的数据保留与复开。
3. 核对书数、原件可读、标题/作者/分类、笔记、进度和待同步状态；失败时保留日志和副本，退出新程序后恢复整套旧备份与旧程序。
4. 迁移后的库不要交给旧程序直接使用。未知 schema/其他应用数据库应拒绝；不要改 `user_version` 强行打开。
5. 宿主 parser 标签与 SDK schema 是两件事。3.40→3.41 的 macOS owner 历史证据不能证明最终六端兼容；
   当前最终包的产品数据、账号/凭据迁移及中断恢复仍待平台实测。

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

已有 [分发依赖/SBOM 库存](READER-DISTRIBUTION-INVENTORY.md) 与
[阅读许可材料检查](READING-LICENSES.md)。库存成功和严格 `release_ready` 成功分别判定；
最终宿主包的许可/SBOM、字体与各平台系统依赖实测仍缺，不宣称已满足 F12。
