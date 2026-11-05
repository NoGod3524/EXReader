# EXReader Studio（Windows 客户端）

从零编写的 Windows 阅读客户端界面，Direct2D + DirectWrite 自绘，只通过公开 SDK 接口
（`exr_library_*`、`exr_pager_*`、`exr_fixed_*`、`exr_render_*`）使用底层，不改动引擎代码。

- 书架：封面网格（内嵌封面 / PDF 首页 / 自动生成的渐变封面）、阅读进度、继续阅读卡片、
  全部 / 最近阅读 / 收藏筛选、书名与作者搜索、右键收藏或移除（窗口内确认，默认取消）、拖拽或对话框导入
- 阅读：居中纸张排版、点击左右区域 / 方向键 / 滚轮翻页、淡入翻页、进度条点击跳转、
  字号与行距、纸白 / 米黄 / 护眼 / 夜间四种背景（设置面板随之换色），自动保存并恢复位置
- 目录：书籍自带目录（EPUB nav / NCX）的抽屉，按层级缩进、标出当前章节，点击跳转
- PDF/CBZ 缩放：放大后页面限制在上下栏之间，可拖动、滚轮或上下方向键平移，滚到页底 / 页顶
  时翻到下一页 / 上一页（倒翻时从页底进入）
- 浅色 / 深色界面，Per-Monitor DPI，Windows 11 标题栏随界面配色
- 无障碍：通过 UI Automation 公开按钮、书籍、目录项和当前页正文，讲述人等屏幕阅读器可以读取并操作；
  翻页时播报页码
- 键盘：Tab / Shift+Tab 在书架和阅读器的控件间移动焦点（带焦点框），Enter 执行；Ctrl+O 导入、Ctrl+F 搜索、
  方向键 / PgUp / PgDn / 空格翻页、Home / End 跳到首尾、Ctrl+加减调字号或缩放、Esc 关闭面板或返回书架

这一基线的 SDK 只提供白底的流式页渲染，界面把黑字白底逐通道映射到所选背景和文字色，
书中插图所在区域（`exr_layout_boxes` 中的图片框）跳过映射、保留原色；插图的透明部分按
原图 alpha（与 SDK 相同的采样方式）把透出的白底换成主题背景色。

这一基线的 SDK 解析 EPUB 包文档时只取书名和语言，书库导入 EPUB 时作者写为空，公开接口
也没有读取 EPUB 作者的函数，所以书架上的 EPUB 不显示作者；需由 SDK 负责人修复。

所有 SDK 调用都在一个后台线程（`src/engine.cpp`），界面线程（`src/ui.cpp`）只发请求、收事件。

## 构建

```sh
cmake --preset reading-library
cmake --build --preset reading-library
cmake --install build/reading-library
cmake -S apps/reader/windows-studio -B build/studio -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_SDK=build/reading-library/stage
cmake --build build/studio
```

运行：`build/studio/exreader-studio.exe [--data 目录] [--trace 文件] [书籍文件 ...]`。默认书库位于
`%LOCALAPPDATA%\EXReader Studio`，与参考宿主的书库相互独立。

`--trace` 在每次界面状态变化后追加一段状态记录，供 `tests/drive.ps1` 在 GitHub Actions 中
驱动窗口（打开、缩放与平移、字号、行距、日夜主题、目录跳转、翻页、返回书架、重新打开、关闭）时核对；`tests/uia.ps1` 以 UI Automation 客户端读取并操作同一窗口；`tests/make-probes.py` 生成所用的
测试 EPUB 与 PDF。
