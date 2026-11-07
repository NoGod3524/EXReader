# 2a 第 6 步证据

[完整验收报告](../../2A-STEP6-ACCEPTANCE.md) · [机器结果](record/primary.json) · [回归](record/regression.json) · [动画/DPI](record/motion.json) · [UIA](record/uia.json)

| 图 | 内容 |
| --- | --- |
| [panel-open-light.png](panel-open-light.png) | 原始紅樓夢，浅色面板 |
| [panel-open-dark.png](panel-open-dark.png) | 原始紅樓夢，深色面板 |
| [selected.png](selected.png) | 原始 Pachinko，第 2 章选中态 |
| [empty.png](empty.png) | 既有无目录夹具，16/650 空状态 |
| [long-1169.png](long-1169.png) | 莎士比亚全集，1,169 项目录 |
| [scrollbar-hover.png](scrollbar-hover.png) | 悬停仍为 5px，只改颜色 |
| [keyboard-focus.png](keyboard-focus.png) | 列表键盘焦点 |
| [negative-one-pixel.png](negative-one-pixel.png) | 反例：正文区改动 1px 可被比较器检出 |
| [cover-light.png](cover-light.png) | main #67 封面修复回归 |
| [cover-dark-focus.png](cover-dark-focus.png) | 深色封面与真实控件焦点环 |

全部由 getter 修复后的新 EXE 重出，来自 DPI 感知的离屏 PrintWindow。整窗 1298×838，客户区 [9,38,1280,800]。成功套件 19 个 GUI 进程，含首次动画断言失败尝试共 20 个，前台观察数均为 0；完整原始 JSON、PNG、QPC CSV、drive 和日志保存在 [measurements.zip](record/measurements.zip)，首次失败保存在包内 `motion-first-attempt/`。[metadata.json](record/metadata.json) 记录源码、二进制、SDK DLL、原始书及规格的 SHA-256；[build.json](record/build.json) 记录 MinGW 与 MSVC 构建结果，[previous/](record/previous/) 保留上轮报告供对照。书本原件不随证据包提交。
