# 0.1.1 验证记录

2026-10-15，美国东部时间。应用代码提交 `ed43882`；之后的提交更新打包、测试工具和文档。

- 浏览器功能：Chromium / Edge、WebKit、WebKit 手机视口，**31 通过、2 跳过**。覆盖 PDF、EPUB、FB2、TXT、RTF、MOBI、DOCX 导入和重开，标注、书签、排版、书名和封面编辑、含封面的 EPUB 导出、备份恢复、内置转换往返及内容隔离。
- 跳过项：Windows WebKit 端口无法解码本地 PCM WAV；相同音频在 Chromium 通过播放进度和重开恢复检查。Apple / Android 的完整音频真机检查未完成。
- 阅读版面：修复分页参数缺少 CSS 长度单位的问题。三个浏览器项目均检查阅读 iframe 使用至少 75% 的阅读区域高度、顶部偏移小于 80 px，并检查书库没有横向溢出，**通过**。
- 生产 PWA：完整缓存、断网重载、打开已导入书籍，**通过**。
- Windows x64：下载 CI 生成的 0.1.1 免安装包，在独立测试目录运行两轮。阅读原创示例、保存书签、退出并重开，书库与书签保留，**通过**。检查原生阅读截图，页边距正常。EXE 约 6.3 MiB，ZIP 约 4.4 MiB，包内版本号为 0.1.1。
- Linux Ubuntu 22.04 x64：AppImage、deb 和使用系统 WebKit 的轻量免安装包构建通过。AppImage 在 Xvfb + Openbox 中运行；deb 的系统运行库程序单独解包启动，检查可见窗口和截图，**通过**。最终轻量包使用与这项原生检查相同的 Debian 程序，二进制内容完全相同，执行权限为 0755。AppImage 压缩包去掉重复 AppDir 后约 79 MiB，内含的 AppImage 内容保持一致。
- macOS 15：通用 app ZIP / dmg 构建通过；核对 Mach-O 包含 Intel x86_64 和 Apple Silicon arm64。ARM64 runner 解压 app、原生启动、截图，**通过**。未完成完整原生阅读、文件导出或公证。
- iOS / iPadOS：ARM64 未签名设备 IPA、ARM64 模拟器 app 构建通过；核对包内版本为 0.1.1。分别安装并启动 iPhone、iPad 模拟器，生成启动截图，**通过**。未完成 Apple 设备签名、真机兼容性、完整原生阅读、音频与导出检查。
- Android 0.1.1：优化签名 APK 的构建和原生界面检查正在运行，结果完成后补充。此前 0.1.0 优化签名 APK 已通过示例阅读、书签、两轮重开持久化、系统保存对话框导出及备份内容核对。
- calibre 桥接：格式白名单拒绝路径穿越输入，Rust 单元检查 1 通过；另装 calibre 后的完整转换尚未验证。

| 检查 | GitHub Actions |
| --- | --- |
| 0.1.1 桌面构建 | [38830888209](https://github.com/NoGod3524/EXReader/actions/runs/38830888209) |
| 0.1.1 Linux / macOS 原生启动 | [38831493976](https://github.com/NoGod3524/EXReader/actions/runs/38831493976) |
| 0.1.1 Apple 构建与模拟器启动 | [38830890998](https://github.com/NoGod3524/EXReader/actions/runs/38830890998) |
| 0.1.1 Android 构建与原生界面检查 | [38830893699](https://github.com/NoGod3524/EXReader/actions/runs/38830893699) |
| 0.1.0 Android 优化包原生检查 | [38830233689](https://github.com/NoGod3524/EXReader/actions/runs/38830233689) |

桌面与 Apple 截图位于 `docs/screenshots/`。自动化书籍样本由 `tests/fixtures.js` 生成；原生检查使用项目原创示例文章。

尚未覆盖复杂商业出版物、压缩 MOBI/KF8 的完整兼容性、多 GB 书库、大型扫描 PDF、DRM / LCP、完整无障碍规范。内置格式转换提取正文，不提供复杂排版和图片的无损往返；当前不包含 OCR、跨设备同步或有声书后台播放管理。
