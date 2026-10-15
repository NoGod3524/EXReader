# 0.1.0 验证记录

2026-10-15，Windows x64。

- 浏览器功能测试：Chromium / Edge、WebKit、WebKit 手机视口，共 **31 通过、2 跳过**。覆盖 PDF、EPUB、FB2、TXT、RTF、MOBI、DOCX 的导入与重开，标注、书签、排版、书名编辑、封面替换、含封面的 EPUB 导出、收藏、备份恢复、转换往返和内容隔离。
- 两个跳过项均为 Windows WebKit 端口的 PCM WAV 播放：该端口宣称支持但实际无法解码。相同音频在 Chromium 通过播放进度和重开恢复测试。不能以这些结果代替 Apple / Android 音频真机测试。
- 生产 PWA 测试：先完整缓存，断开网络，重新载入，打开此前导入的书籍，**通过**。静态资源缓存忽略静态服务器的 CORS `Vary` 头，根路径离线导航返回已缓存的 `index.html`。
- Windows 原生 EXE：启动、导入原创示例、阅读、保存书签、返回书库，退出进程；再次启动确认书库和书签保留，**通过**。使用独立测试目录，不向交付书库写入测试数据。
- Windows 原生 calibre 命令：格式白名单拒绝路径穿越输入，**通过**。Rust 单元测试 **1 通过**。
- Windows 免安装包构建：Tauri release 构建成功。运行使用系统 WebView2。

未验证：Linux / macOS 原生包、Android APK、iOS / iPadOS 原生签名与真机兼容性；另装 calibre 后的完整真实转换；复杂商业出版物、压缩 MOBI/KF8、多 GB 书库、大型扫描 PDF、DRM / LCP、完整无障碍规范。Android 本机初始化因缺少 Java / Android 工具链未能运行，原生移动项目由相应平台的 Tauri CLI 初始化。

自动化样本均由 `tests/fixtures.js` 生成。界面截图位于 `docs/screenshots/`。测试命令参见 README。
