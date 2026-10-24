# Android 正式宿主账号与接收

本包把单个 WebDAV 账号、手动同步、取消、断开和远端书籍的显式接收接入原 `org.exreader.host.MainActivity`，入口在 More → 同步。账号设置与云盘书目位于独立面板，书架和阅读页不增加常驻工具栏。

受测源码 `ed9ff5ffc3608971bb19020f1ec07496a79d9710` 在 [正式 UI run 40090470041](https://github.com/NoGod3524/EXReader/actions/runs/40090470041) 通过，API26 编译、API34 x86_64 模拟器实际执行。[记录](validation/reader-host-session-android.json) 授予本包账号/接收界面与定向语义范围。独立原生壳的 [18 捕获验收](validation/reader-reading-state-android.json) 继续保留。

同一源码的 [原 Android 完整回归 40090470061](https://github.com/NoGod3524/EXReader/actions/runs/40090470061) 与 [Windows/Linux codec 40090470091](https://github.com/NoGod3524/EXReader/actions/runs/40090470091) 均成功。正式 UI 作业 `120861917685` 保留 SDK 原件导出 8 项、18 真实捕获原生壳 12 组、原宿主 17 项及两次进程中断恢复、DAV 91+4 原套件，另执行 16 项真实控件检查：首进程 6、Keystore 重启进程 5、仅本次凭据重启进程 1、语义进程 4。四个 PID 为 5712 / 5859 / 6033 / 6168。

正式工件 `12559220856` 为 107771689 B，SHA-256 `5d1c1e3487b1dbcf5903bef102c7a721b5edd05ad977f0ff92b693c7bb794bf6`，有效期至 2027-01-22T11:34:49Z。其余三份同源工件的身份、大小和散列，以及全部 16 项具名结果登记在 JSON。

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

四项定向检查均已实际通过。前翻后真实 frame 的 index 从 0 到 1、start 从 0 到 415；后翻回到第一页。字体状态与 SDK glyph font 均从 24 到 28，系统 font_scale=2 时 Organizer 仍可到达且底层书架从节点树移除。共保存六份节点树及 PNG，Actions 核验 PNG 字节和散列。74 次应用私有文件读取未发现 fixture 凭据明文；首三阶段本机 TXT 进度保持 8、SDK notes 复制为 0，语义阶段随后显式翻页和调整字号。

## 运行配置与交付身份

这是沿用原 Android 宿主的共享 SDK 构建，不是桌面 `reading-core` 裁剪 profile。工作流显式声明 `EXR_ENABLE_AUDIO=ON`、`EXR_ENABLE_AAC=OFF`；源码中 `EXR_ENABLE_MP3` 默认 ON。受测工件没有归档 SDK CMakeCache，因此这三个实际 cache 值登记为缺测。冻结 `CMakeLists.txt` 明确要求现有 JNI 同时启用 audio/PDF；core-only SDK 须关闭 JNI。当前没有修改这些构建选项或冻结源码。

[只读材料诊断 40091262964](https://github.com/NoGod3524/EXReader/actions/runs/40091262964) 按正式工件 ID、字节和 SHA-256 重新核对 ZIP 后，在 Actions 读取 ELF。安装后的 engine/JNI 分别为 22258128 / 176496 B；Debug 与 Release APK 内分别为 5545208 / 40392 B。engine 的 NEEDED 是 `libOpenSLES.so, libm.so, libdl.so, libc.so`；JNI 是 `libexreader.so, libm.so, libdl.so, libc.so`。安装/包内各自 SHA-256 全部登记在 JSON。该诊断保持 `diagnostic_only=true, accepted=false`，正式授予仍归属 ed9 原 producer。

`b385f77e4c98cb9227fe765a5bb99defd5d33dd3` 随后只增加 audit 真实 cache/运行库材料记录和 workflow cache 工件路径；其重复运行 40090641782 / 40090641830 / 40090641779 已取消，未获正式授予。`06822003` 只修改固定工件检查脚本，实际仅执行了上述诊断。当前交付 HEAD 相对 ed9 的非文档净差异是这三个文件：`reader-host-session-android.yml`、`audit.py`、`inspect.py`；不能将它称作纯文档 HEAD 或已通过的整包。主线应选择实际通过的 ed9，证据文档可独立摘取。原失败、修复及取消记录全部保留。
