# DeckMark 设计令牌（EXReader UI 对标来源）

**来源**：`C:\Users\Oscar\EZNotes\src\index.css`（DeckMark 应用源码，`--` 变量定义在 `:root` L1–L42，深色在 L44 起，按钮在 L117 起）。
**用途**：EXReader 的 2a 外壳（顶栏、设置浮层、目录面板）一律使用这套令牌，**不再使用 2026-11-04 那套 Google 风格的值**。

## 浅色

| 令牌 | 值 | 用途 |
|---|---|---|
| `--bg` | `#f5f5f2` | 应用底色（暖白，不是纯白） |
| `--surface` | `#ffffff` | 卡片/面板 |
| `--surface-2` | `#efeeea` | 悬停底、次级面 |
| `--surface-3` | `#e7e6e1` | 按压底、分隔面 |
| `--desk` | `#ebeae6` | 更深一层的桌面底 |
| `--text` | `#1b1b1f` | 正文主色 |
| `--text-2` | `#5c5c65` | 次级文字 |
| `--text-3` | `#8b8b94` | 三级/占位 |
| `--line` | `rgba(20,20,32,0.075)` | 发丝线 |
| `--line-strong` | `rgba(20,20,32,0.13)` | 控件描边 |
| `--accent` | `#4553e0` | 强调色（靛蓝） |
| `--accent-hover` | `#3946cc` | |
| `--accent-soft` | `rgba(69,83,224,0.10)` | 选中底 |
| `--accent-softer` | `rgba(69,83,224,0.06)` | 极浅强调底 |

## 深色

| 令牌 | 值 |
|---|---|
| `--bg` | `#141416` |
| `--surface` | `#1e1e21` |
| `--surface-2` | `#28282c` |
| `--surface-3` | `#313136` |
| `--desk` | `#0e0e10` |
| `--text` | `#f2f2f4` |
| `--text-2` | `#b3b3bc` |
| `--text-3` | `#7d7d87` |
| `--line` | `rgba(255,255,255,0.075)` |
| `--line-strong` | `rgba(255,255,255,0.13)` |
| `--accent` | `#7c88ff` |
| `--accent-hover` | `#929cff` |

## 圆角 / 阴影 / 动效

```
--radius      14px    面板、浮层
--radius-sm    9px    按钮、输入、列表行
--radius-lg   18px    大容器
--ease        cubic-bezier(0.2, 0.8, 0.2, 1)

--shadow-sm  0 1px 1px rgba(16,16,28,.04), 0 1px 3px rgba(16,16,28,.06)
--shadow-md  0 1px 2px rgba(16,16,28,.05), 0 8px 20px -6px rgba(16,16,28,.12)
--shadow-lg  0 2px 6px rgba(16,16,28,.06), 0 22px 48px -12px rgba(16,16,28,.24)
--page-shadow 0 0 0 1px rgba(16,16,28,.05), 0 2px 10px -2px rgba(16,16,28,.12)
```

## 字体栈

```
-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI Variable Text', 'Segoe UI',
'PingFang SC', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif
```

正文字号 14px / 行高 1.45（DeckMark 的 UI 密度）；**EXReader 正文另按排版规格（17px、行高 1.6），UI 文字沿用上表**。

## 按钮（`--radius-sm` + `--line-strong` 描边 + `--shadow-sm`）

```
高度 34px，左右内边距 14px，字重 550，圆角 --radius-sm(9)
默认：background var(--surface)；border 1px var(--line-strong)；color var(--text)
hover：background var(--surface-2)
active：transform translateY(0.5px)
disabled：opacity .4
primary：background var(--accent)；color #fff；border transparent；
         内高光 inset 0 1px 0 rgba(255,255,255,.16) + 外投影
ghost：无边框无阴影，color var(--text-2)，hover 时 background var(--surface-2)
```

## 与 EXReader 现行规格的差异（必须替换）

| 项 | 现行（2026-11-04，待废） | DeckMark |
|---|---|---|
| 页面底 | `#FFFFFF` 纯白 | `#f5f5f2` 暖白 |
| 强调色 | `#1A73E8` | **`#4553e0`**（深色 `#7c88ff`） |
| 圆角 | 8 / 10 / 14 | **9 / 14 / 18** |
| 发丝线 | `rgba(0,0,0,.06)` | **`rgba(20,20,32,.075)`** |
| 按钮 | 纯色块、无描边 | **1px `--line-strong` 描边 + `--shadow-sm` + 字重 550** |
| 界面字体 | 未指定 | SF Pro / Segoe UI Variable / PingFang SC / YaHei UI |
| 动效曲线 | ease-out | **`cubic-bezier(.2,.8,.2,1)`** |

**铁律**：令牌值只能来自本文件。若要偏离，必须回到 DeckMark 源码确认，不得凭印象新增。
