# Android 正式宿主账号与接收

本包把单个 WebDAV 账号、手动同步、取消、断开和远端书籍的显式接收接入原 `org.exreader.host.MainActivity`，入口在 More → 同步。账号设置与云盘书目位于独立面板，书架和阅读页不增加常驻工具栏。

这是未验收候选；[记录](validation/reader-host-session-android.json) 在云端完整通过前保持 `accepted:false`。独立原生壳的 [18 捕获验收](validation/reader-reading-state-android.json) 保留，不能替代正式界面出口。

开发构建通过 `-PexrSync=true` 启用，并传入已安装的 `exrSdk`、`exrProduct`、`exrDav`、`exrSideload` 前缀。现有宿主回归构建默认不启用这个可选包。Gradle 引用原 Java WebDAV 与 Credentials 模块；SDK 版本和 ABI、产品 schema1 均不变。

`exreader_host` 与原 `exreader-jni` 继续引用同一安装后的共享 `libexreader.so`。宿主只消费已安装公开 Sideload 目标的归档和头目录，不引入它的静态 SDK 依赖闭包；Actions 保存该归档未解析依赖、实际链接 map、动态依赖和运行时公开 SDK 函数归属。产品侧仍使用 `libexreader_product.so` 内唯一的独立产品 SQLite。

凭据仅经 AndroidKeyStore 的既有 AES-GCM 存储保存。账号 UUID 与精确 HTTPS 根地址可持久化，Authorization 不写普通文件；“仅本次使用”须由用户明确选择。移除凭据保留书籍和书库绑定。已有书库不会静默切换到另一个账号或地址。

Session 自有后台 worker；界面不借用 SDK 指针。原件先在既有 SDK worker 上公开回读、核验、导出，结束借用后再启动网络。取消和后台关闭不等待网络；观测到 CLOSED 后才销毁句柄。显式重试保留 history/outbox，结束的一轮不会自动再扫描。

远端书目按 keyset 分页，每页最多 50 条。只有完整安全的唯一非删除 head 可接收。用户确认后，宿主先以 expected head 投影当前 metadata，再核验私有缓存、释放既有阅读句柄、公开 SDK 去重导入，核对 SDK 原件后再次检查 head，保存路径并附加本机映射。SDK、路径设置和产品库是独立提交；失败保留已经提交的原件，可重试接收。接收不复制产品标注为 SDK notes，不导航到远端阅读位置。

云端工作流保留原 18 捕获、原宿主 17 项与两个进程中断恢复、SDK 原件导出和 Android DAV 检查，并增加实际 Activity 操作、Keystore 跨进程读取、受阻请求取消、后台关闭/重开、显式 Receive、精确重试、凭据移除及仅本次凭据的重启丢失。fixture CA 与 native registry 探针只进入 Debug；Release 单独检查。

本阶段不授予产品标注界面、用户显式采纳阅读状态、真机或六平台产品互通。后续按主线固定模块源接入这些功能。

## 定向语义修复

G15 的固定源码 `2bdfee69`、[producer 40082957400](https://github.com/NoGod3524/EXReader/actions/runs/40082957400) 完成了 15 项审计，保留 11 pass / 4 fail、`accessibility_accepted:false`。本宿主按其实际观察修复四处根因：两个状态区声明 polite；ReaderView 暴露并处理前后翻页动作；字号/缩放控件在 API30+ 声明当前值，API26 使用内容描述回退；Organizer 模态显示时移走背景输入焦点并从语义树隐藏书架，关闭后恢复，不改内部排版。

新账号面板使用原生 AlertDialog。自有云端出口增加四项定向语义与真实 200% 系统字号检查，保留原始节点树和截图。这些检查仍不授予完整 G15 审计、TalkBack 语音或真机通过；完整 G15 将在主线同源集成后重跑。
