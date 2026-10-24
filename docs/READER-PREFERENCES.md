# 阅读设置（F3）：`EXReaderPreferences 0.1.0`

独立可选安装包，公开 C ABI `reader_preferences.h`。不依赖 SDK 归档、产品目录、修订、
阅读状态或宿主设置文件；默认 reading 构建不加入它。源码在
`apps/reader/preferences/`，测试在 `tests/reader_preferences/`，工作流为
`.github/workflows/reader-preferences.yml`。本文件说明契约；**验收状态见末节。**

## 范围与非目标

- 只保存、校验、导入阅读外观值，并提供宿主读取后的纯查询。不创建 layout、不分页、
  不绘制、不注册平台主题通知、不写 SDK 表、产品 schema、同步 wire 实体或宿主 profile。
- 设置是设备本地数据；每台设备使用调用者给出的 app 私有独立文件。跨设备携带由宿主
  自行决定，本包不定义同步实体，也不把本机 SDK 行号当身份。
- “跟随系统”只保存 `system` 枚举；当前系统状态由宿主在每次调用
  `reader_preferences_effective_theme` 时传入。包内没有观察者、后台线程或定时器。
- 单调用者 worker 串行使用；包内不加锁文件、watcher、远端配置、云服务、插件系统或数据库。

## 字段、默认值与合法区间

默认值来自冻结 SDK 3.40.0 的 `exr_layout_defaults()`（24 pt / 1.6 / 12 pt / 48 pt），
其余为包的确定性默认；不改任何宿主现有默认。

| JSON 键 | API 字段 | 默认 | 合法区间 | 单位 | 重排 | 固定页 |
| --- | --- | --- | --- | --- | --- | --- |
| `font_size` | `font_size` | 24 | 4..256 | pt | 可用：`exr_layout_options.font_size` | 不使用 |
| `line_spacing` | `line_spacing` | 1.6 | 1..5 | 倍数 | 可用：`exr_layout_options.line_height` | 不使用 |
| `paragraph_spacing` | `paragraph_spacing` | 12 | 0..1024 | pt | 可用：`exr_layout_options.paragraph_spacing` | 不使用 |
| `margin` | `margin` | 48 | 0..1024 | pt | 可用：`exr_layout_options.margin`（四边同值） | 不使用 |
| `theme` | `theme` | `light` | `light`/`dark`/`system` | 枚举 | 宿主外观，无 SDK 布局参数 | 宿主外观 |
| `light_foreground` | `light_foreground[4]` | `#1A1A1AFF` | `#RRGGBB`/`#RRGGBBAA` | sRGB RGBA | 宿主绘制，无 SDK 布局参数 | 宿主绘制 |
| `light_background` | `light_background[4]` | `#FFFFFFFF` | 同上 | sRGB RGBA | 宿主绘制 | 宿主绘制 |
| `dark_foreground` | `dark_foreground[4]` | `#E6E6E6FF` | 同上 | sRGB RGBA | 宿主绘制 | 宿主绘制 |
| `dark_background` | `dark_background[4]` | `#101010FF` | 同上 | sRGB RGBA | 宿主绘制 | 宿主绘制 |
| `page_turn_direction` | `page_turn_direction` | `ltr` | `ltr`/`rtl`/`vertical` | 枚举 | 宿主导航，无 SDK 布局参数 | 宿主导航 |
| `page_turn_input` | `page_turn_input` | `tap` | `tap`/`swipe`/`tap_and_swipe`/`hardware_keys` | 枚举 | 宿主操作，无 SDK 布局参数 | 宿主操作 |
| `fixed_page_zoom` | `fixed_page_zoom` | 100 | 25..400 | 百分比整数 | 不使用 | `exr_fixed_render` 的 `scale = percent/100` |

数值必须有限：NaN、±Inf、溢出指数、负数或越界均被拒绝。枚举只接受表内字符串；颜色只接受
`#` 后 6 或 8 位十六进制。`fixed_page_zoom` 是整数，100.5 被拒绝。

### 与现有 SDK 布局参数的对应

```c
exr_layout_config config = exr_layout_config_defaults(); /* 宿主自己的默认，不改 */
config.page.font_size = preferences.font_size;
config.page.line_height = preferences.line_spacing;      /* 倍数，不是像素 */
config.page.paragraph_spacing = preferences.paragraph_spacing;
config.page.margin = preferences.margin;                 /* SDK 只有统一 margin */
/* width/height 仍是宿主视口，不从设置文件读取。 */
```

包只校验字段包络，**不知道视口**。宿主在调用 `exr_layout_create*` 前还必须满足 SDK 的组合
约束：`width,height` 在 32..16384，`margin` 非负，且

```text
width  - 2 * margin >= font_size * 1.5
height - 2 * margin >= font_size * line_spacing
```

固定页不使用字号、行距、段距或页边距；`exr_fixed_render(document, page, percent / 100.0, ...)`
使用缩放。固定页背景由宿主在其画布上绘制，`exr_fixed_render_options` 的 `background`
不是本包的设置。翻页方向与操作偏好只供宿主导航；SDK 没有对应布局字段。

### 当前宿主默认（只记录，不修改）

| 宿主 | 现有默认/范围 | 证据 |
| --- | --- | --- |
| Windows 示例 | 基准 28 pt、`line_height=1.5` | `examples/reader.c` |
| Apple 示例 | 28 pt，18..48，margin 36 | `examples/apple/HostModel.swift` |
| Linux 示例 | 24 pt，12..48，zoom 100 ±25 | `examples/linux/reader.c` |
| Android 示例 | 24 / 1.6 / 12 / margin 48 | `examples/android/.../EXReader.java` |

这些宿主值保持逐字不变。旧设置只能由宿主显式调用
`reader_preferences_import_legacy` 迁移；未列入 `present` 的字段保持调用者当前值，未知位
返回 `ARGUMENT` 且不应用任何字段，绝不静默重置。

## 文件格式

canonical 文档是 UTF-8 JSON 对象，固定 14 个键，无注释、无未知键、无重复键、无转义；
可接受 UTF-8 BOM。最大 65536 字节（`max_file_bytes` 可下调）。浮点以 6 位小数写出并去掉
尾零，避免 locale 小数点差异；读写往返对 6 位小数以内的 UI 值稳定。

```json
{
  "format": "exreader-preferences",
  "format_version": 1,
  "font_size": 24,
  "line_spacing": 1.6,
  "paragraph_spacing": 12,
  "margin": 48,
  "theme": "light",
  "page_turn_direction": "ltr",
  "page_turn_input": "tap",
  "fixed_page_zoom": 100,
  "light_foreground": "#1A1A1AFF",
  "light_background": "#FFFFFFFF",
  "dark_foreground": "#E6E6E6FF",
  "dark_background": "#101010FF"
}
```

未知 `format_version` 返回 `VERSION`，load 不改内存、不改磁盘；调用者保留原文件。
缺失字段、截断、NUL/非 ASCII 字符串、非法颜色/枚举、尾随字节均为 `FORMAT`。
超过上限为 `LIMIT`。

## API、所有权与错误

- `reader_preferences_defaults()` 返回值；`reader_preferences_validate()` 只校验字段与
  `struct_size`/`abi_version`/`reserved`。
- `reader_preferences_load(path, inout, options, error)`：先读完整文件、解析、校验，最后才
  整体替换 `*inout`。任何失败（含取消、未知版本、超限、IO）都保持 `*inout` 逐字节不变。
- `reader_preferences_save(preferences, path, options, error)`：先 `validate`；失败不写任何
  文件。成功才返回 `OK`。
- `reader_preferences_import_legacy(preferences, legacy, report, error)`：事务式；先校验合并
  结果，再一次性赋值。失败时 `preferences` 与 `report` 都不变。
- `reader_preferences_effective_theme(preferences, system_theme)`：纯函数；`system` 用宿主
  传入的 `light`/`dark` 解析，非法系统值回退 `light`。
- 路径、结构体和回调上下文都是借用，只在调用期间有效；包不保留指针，不分配返回对象。
- `reader_preferences_error` 可零初始化；函数入口会清空。错误消息为 UTF-8、NUL 结尾、
  最长 191 字节；`offset` 是文档内字节偏移，`system_error` 是 `errno` 或 `GetLastError`。
- 状态：`OK`、`ARGUMENT`（空指针/结构尺寸/枚举/保留字）、`IO`、`FORMAT`、`VERSION`、
  `RANGE`（NaN/Inf/越界）、`CANCELLED`、`LIMIT`。

## 原子保存、取消与并发

保存顺序：同目录临时文件 → 写满 → `fflush`/`FlushFileBuffers`/`fsync` → 关闭 →
（取消检查）→ 原子替换（POSIX `rename`，Windows `MoveFileExW(REPLACE_EXISTING|WRITE_THROUGH)`）
→ POSIX 目录 `fsync`（尽力）。任一步失败或取消都会删除临时文件，上一份有效文件保持完整。
取消只在替换前返回 `CANCELLED`；替换成功后即使调用者再取消也返回 `OK`，不谎报失败。

- **单调用者**：同一进程内一个 worker 串行调用；包不创建线程，也不做进程内互斥。
- **两个调用者**：不合并、不锁文件。每个保存都是完整临时文件 + 原子替换，跨进程最后完成者
  生效；读者只会看到旧值或新值，不会看到半文件。并发保存的顺序未定义，语义是
  last-complete-writer-wins。需要“后写覆盖前写”的宿主必须自己串行化。
- **真实终止**：替换前被杀，目标仍是旧值；替换后被杀，目标是完整新值；残留临时文件不参与
  load，宿主可按自己的清理策略删除。测试用确定性暂停钩子只编译进测试 worker，安装包不含。

## 验证出口（工作流 `reader-preferences.yml`）

固定受测 source，检查共同起点 `c3511a011eefbf1fba1d20908f000cef22b1ced2` 为祖先、
SDK 保护树（`9854061...`）、产品 schema `001_catalog.sql`（`f32bb8aa...`）及既有宿主
（`examples/` 与 `apps/reader/` 其他模块）逐字未变，改动路径只在 F3 归属内。

Windows、Linux、macOS 各自安装包后，从安装位置编译 C 与 C++ 消费者，并用测试 worker 运行为
跨进程场景。覆盖：默认值；每个字段的最小/最大与越界；NaN/Inf/超大指数；非法枚举/颜色/键；
截断、NUL、坏 UTF-8、空文件、超 64 KiB、未知版本且原文件字节不变；Unicode 路径；
跨进程重开；保存后取消/替换前注入失败/替换前被杀/替换后被杀；两个进程各 120 次并发保存；
旧设置显式导入与未知位拒绝；安装头与源码逐字一致。测试不把配置模块写成主题 UI 或读屏验收。

## 验收状态

### root 独立审查

原交付`6f33caf8`、run`40065361635`三平台16组检查及严格工件核对通过，原分支与
文档HEAD`f453af14`保持不变。审查分支只新增回归后的源码`35fc72c3`、
run`40067107414`保留：原16组继续通过，新增4组在云端失败，严格汇总正确拒绝。

修复范围为拒绝JSON数值前导零、按有效数字解析长小数而不吞掉指数值、可空error参数
不改变返回状态，以及调用者只能降低64 KiB文件上限。公开结构/默认设置与宿主不改；
新增回归逐项确认失败加载保持调用者记录及文件不变，并保留原16组全部运行。
固定实现须在同一source/run/attempt三平台20组及严格汇总通过后才授予审查验收。

审查修复源码`1f51b4066cd705a670b3139061336c298e479081`，run
[`40067465230`](https://github.com/NoGod3524/EXReader/actions/runs/40067465230)，attempt1，
三平台各20/20、四作业全部成功；严格作业`120793748419`重新散列三ZIP并要求完整20个
具名检查逐项成功、source/run/attempt一致及平台结果一致，`accepted=true, problems=[]`。
原16组与新增4组同次执行，不拼原交付通过项；原三平台失败回归记录与工件均保留。

2026-10-24，run [40065361635](https://github.com/NoGod3524/EXReader/actions/runs/40065361635)
attempt 1 在 source `6f33caf83bfb845e27db6382edc5ee100d8db954` 上三平台通过：

| 平台 | job | 结果 |
| --- | --- | --- |
| Linux（ubuntu-22.04） | 120787360078 | 16/16 |
| Windows（windows-2022） | 120787360085 | 16/16 |
| macOS（macos-14） | 120787360075 | 16/16 |

三份工件分别为 Linux 102,487 字节 / `94b95a68…adcf`、Windows 393,600 字节 /
`5c2202ef…2bf5`、macOS 86,276 字节 / `80ef81ab…e983`；strict summary 作业比较了三平台
同名检查，结果为一致。安装头 8,493 字节、SHA-256 `dc91755d…d68a`。

该授予只覆盖所列平台上的本包接口。宿主 UI、产品性能、六平台互通与完整产品均未由此验收；
本包也不是主题 UI 或读屏验收。`docs/validation/reader-preferences.json` 记录本次运行的
source/run/attempt、工件、job 与逐项检查。
