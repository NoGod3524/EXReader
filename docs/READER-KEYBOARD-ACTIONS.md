# READER-KEYBOARD-ACTIONS：原生快捷键与输入焦点动作映射

本包提供一个小型纯状态组件：把**平台原生按键事件 + 宿主实际观察到的焦点/模态状态**换算成
**动作**（上一页/下一页/搜索/返回/目录/书签），并把"这个事件归谁"的结论交回宿主。组件自身
**不执行动作、不注册全局热键、不安装钩子、不移动焦点、不读取设备**。

- 固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`
- 分支：`codex/reader-keyboard-actions`
- 包：`EXReaderKeyboardActions 0.1.0`，公开 C ABI `READER_KBD_ABI_VERSION 1`，另有 header-only C++ 包装
- 依赖：仅 `EXReaderPreferences 0.1.0`（读取 `page_turn_direction` / `page_turn_input` 两个既有枚举值）
- 不改：SDK `9854061be331fe603a1822d9b2b36ee357154927`（3.40.0/ABI1）、产品 schema 1、既有 wire v1、reading anchor v1/v2、四套宿主快捷键

## 公开契约

### 输入

```c
typedef struct {           /* reader_kbd_event */
  uint32_t struct_size;    /* == sizeof(reader_kbd_event) */
  uint32_t phase;          /* DOWN / UP */
  uint32_t key;            /* CHAR、方向键、PageUp/Down、Space、Enter、Esc、Backspace、Tab、BROWSER_BACK */
  uint32_t codepoint;      /* key == CHAR 时的字符；A-Z 折叠为 a-z；代理区与 >0x10FFFF 是 ARGUMENT */
  uint32_t modifiers;      /* SHIFT/CTRL/ALT/META/ALTGR；锁定键不是修饰键 */
  uint32_t repeat;         /* 非零：操作系统对同一按住的键的自动重复 */
} reader_kbd_event;

typedef struct {           /* reader_kbd_context，由宿主按该事件发生时的真实状态填写 */
  uint32_t struct_size;
  uint32_t focus;          /* READER / TEXT_INPUT / MODAL / CONTROL */
  uint32_t composing;      /* 非零：IME 组词进行中 */
  uint32_t window_active;  /* 非零：阅读窗口是该事件的键盘所有者 */
} reader_kbd_context;

typedef struct {           /* reader_kbd_config */
  uint32_t struct_size;
  uint32_t platform;             /* WINDOWS / LINUX / APPLE / ANDROID */
  uint32_t page_turn_direction;  /* reader_preferences_turn_direction */
  uint32_t page_turn_input;      /* reader_preferences_turn_input */
  uint32_t flags;                /* ALWAYS_PAGE_KEYS、NO_REPEAT_PAGING */
} reader_kbd_config;
```

### 输出

```c
typedef struct {           /* reader_kbd_result，库每次调用都会写满 */
  uint32_t struct_size;
  uint32_t action;         /* NONE/PAGE_PREVIOUS/PAGE_NEXT/SEARCH/BACK/CONTENTS/BOOKMARK */
  uint32_t disposition;    /* PASS：原样交给原生焦点所有者；CONSUME：不再转交 */
  uint32_t reason;         /* ACTION/UNMAPPED/MODIFIER_CONFLICT/TEXT_INPUT/MODAL/COMPOSING/
                              INACTIVE/PAGE_KEYS_DISABLED/CONTROL_OWNS/REPEAT_SUPPRESSED/
                              REPEAT_LIMIT/ORPHAN_REPEAT/KEY_UP_SWALLOWED/KEY_UP/DECLINED */
  uint32_t repeat_actions; /* 该次按住已由重复键产生过多少个翻页动作 */
} reader_kbd_result;
```

映射表（精确修饰键匹配；多按任何其它修饰键即 `MODIFIER_CONFLICT`）：

| 原生键 | 条件 | 动作 |
| --- | --- | --- |
| Right / Left | 无修饰键，LTR | 下一页 / 上一页 |
| Right / Left | 无修饰键，RTL | 上一页 / 下一页 |
| Down / Up | 无修饰键，仅 `TURN_VERTICAL` | 下一页 / 上一页 |
| PageDown / PageUp | 无修饰键 | 下一页 / 上一页 |
| Space | 无修饰键 / Shift | 下一页 / 上一页 |
| Esc、BROWSER_BACK | 无修饰键 | 返回 |
| Alt+Left | 仅非 Apple 平台 | 返回 |
| Ctrl+F（Apple：Cmd+F） | 精确主修饰键 | 搜索 |
| Ctrl+T / Cmd+T | 精确主修饰键 | 目录 |
| Ctrl+D / Cmd+D | 精确主修饰键 | 书签 |
| Cmd+[ | 仅 Apple | 返回 |

翻页类动作还要求 `page_turn_input == HARDWARE_KEYS`，除非设置了 `ALWAYS_PAGE_KEYS`；
命令类动作不受输入模式限制。`FOCUS_CONTROL` 下 Space 与 Enter 永远归该控件（`CONTROL_OWNS`），
即使带 Shift，因此按钮/列表激活与 Shift+Space 不会被抢。`TEXT_INPUT`、`MODAL`、`composing`、
非活动窗口一律 `PASS`，编辑键原样留给原生焦点所有者。

### 内存归属、线程、重入、错误、取消、提交边界

- **内存**：`reader_kbd_create` 分配一个不透明对象，调用者用 `reader_kbd_destroy` 释放；
  传进去的结构体都是调用者拥有的值，库只读不存；返回值都是纯值，不指向库内存。
- **线程**：对象属于创建它的线程。其它线程上的任何调用返回 `WRONG_THREAD` 且不触碰状态；
  不同对象互不共享状态。
- **重入**：`reader_kbd_dispatch` 在持锁状态下同步调用宿主处理器；处理器执行期间对同一对象的
  任何调用（translate/dispatch/cancel/set_config/destroy/held_count）返回 `REENTRANT` 且不改变任何状态。
- **错误**：结构体尺寸不符、枚举越界、码点非法都返回 `ARGUMENT`；任何错误状态都让对象**逐字节不变**，
  并把 result 清零为 `PASS/UNMAPPED`。
- **取消**：`reader_kbd_cancel` 是唯一取消原语（窗口失活、焦点转移时调用），它忘掉所有已消费的
  key-down，使后续重复与抬起回到新的焦点所有者；`dropped` 可为 NULL。
- **提交边界**：状态在**副本**上计算；宿主处理器返回非零才提交，返回零视为拒绝（`PASS/DECLINED`），
  既不提交也不吞掉配对的 key-up。没有处理器时立即提交。
- **硬上限**：`READER_KBD_MAX_HELD = 8`（再多按下一条会淘汰最旧的一条，被淘汰者的 key-up/重复转交新焦点），
  `READER_KBD_MAX_REPEAT_ACTIONS = 64`（到顶后仍 `CONSUME` 并报 `REPEAT_LIMIT`，配对关系不变）。
  两个上限都在代码里强制，绝不增长。

### C++ 包装

`reader_keyboard_actions.hpp` 提供 move-only 的 `reader::KeyboardActions`：`translate`、
`dispatch`（处理器抛出的异常在 extern-C trampoline 里转成"拒绝"，对象保持可用）、`cancel`、
`set_config`、`held_count`。跨线程析构返回 `WRONG_THREAD`，包装器**故意不释放**该对象（记录在案，
不制造竞态）。

### 原生翻译器

纯函数，不包含任何平台头、不读设备、不分配；失败时把输出清零：

- `reader_kbd_event_from_win32(message, wparam, lparam, win32_modifiers, out, composing)`：
  WM_KEYDOWN/UP、WM_SYSKEYDOWN/UP，lParam 位 30 为 repeat，VK_PROCESSKEY 置 composing，
  Ctrl+右 Alt（无左 Alt）识别为 AltGr，锁定键按设计丢弃。
- `reader_kbd_event_from_x11(type, keysym, state, repeat, out)`：KeyPress/KeyRelease，
  Mod1→ALT、Mod4→META、Mod5→ALTGR；repeat 由宿主按"无 KeyRelease 的同键 KeyPress"提供。
- `reader_kbd_event_from_apple(type, key_code, flags, unmodified_codepoint, is_repeat, out)`：
  keyDown/keyUp，Command→META，Function/NumericPad/CapsLock 位丢弃。
- `reader_kbd_event_from_android(action, key_code, meta_state, repeat_count, out)`：
  只有数字向量覆盖，不涉及真机。

## 构建与安装（只在 GitHub Actions 执行）

```
cmake -S apps/reader/preferences -B build/kbd-pref -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=build/kbd-pref-stage
cmake --build build/kbd-pref && cmake --install build/kbd-pref
cmake -S apps/reader/keyboard-actions -B build/kbd-package -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_PREFIX_PATH=build/kbd-pref-stage -DCMAKE_INSTALL_PREFIX=build/kbd-stage
cmake --build build/kbd-package && cmake --install build/kbd-package
```

安装前缀提供 `EXReaderKeyboardActionsConfig.cmake`（`find_dependency(EXReaderPreferences 0.1.0 EXACT)`）
与 `EXReaderKeyboardActions::reader_keyboard_actions` 目标。消费者工程只加前缀，不加源码目录：

```
cmake -S tests/reader_keyboard_actions/consumer -B build/kbd-consumer -G Ninja \
      -DCMAKE_PREFIX_PATH=build/kbd-stage\;build/kbd-pref-stage
cmake -S tests/reader_keyboard_actions/probes   -B build/kbd-probe   -G Ninja \
      -DCMAKE_PREFIX_PATH=build/kbd-stage\;build/kbd-pref-stage
```

宿主接入范例（真实代码，见 `tests/reader_keyboard_actions/probes/`）：窗口过程/GDK 键处理/
`NSWindow sendEvent:` 把原生事件交给 `reader_kbd_dispatch`，`CONSUME` 就不再走默认处理，
`PASS` 就原样交给默认处理；焦点转移、失活时调用 `reader_kbd_cancel`。本包不改任何现有宿主的快捷键表。

## 验证

工作流 `.github/workflows/reader-keyboard-actions.yml`，三个桌面平台各一个作业：

| 平台 | 原生 probe | 真实事件来源 |
| --- | --- | --- |
| ubuntu-22.04 | GTK3 窗口 + `GtkEntry` + 模态 `GtkDialog` | Xvfb + XTest 注入真实 X11 按键，GDK 报告修饰键状态 |
| windows-2022 | Win32 顶层窗口 + EDIT 子类化 + 模态窗口 | `SendInput` 注入真实键盘输入，`GetKeyState` 读修饰键 |
| macos-14 | `NSWindow`（`sendEvent:` 拦截）+ `NSTextField` + sheet | 真实 `NSEvent`（含 `isARepeat`）经 `NSApp sendEvent:` 派发 |

每个平台 41 项具名结果：20 项安装后 C 消费者、7 项安装后 C++ 消费者、14 项原生 probe。
probe 的 14 项同名覆盖：窗口就绪、下一页、上一页、命令搜索、Shift+Space、修饰键冲突放行、
key-up 吞掉、自动重复上限、编辑框保留编辑键、编辑框命令放行、模态保留按键、焦点转移取消按住、
失活取消、IME 组合放行。

`tests/reader_keyboard_actions/check_keyboard.py` 在**读任何输出前**固定了上述用例名集合与
只允许的 SKIP 名单，集合不符或出现 FAIL 即拒绝。`tests/reader_keyboard_actions/check_artifacts.py`
在同一次 run/attempt 内通过 API 取作业与工件，下载每个平台 ZIP、重算字节数与 sha256、解包读
`keyboard-evidence/result.json`，校验 source/run/attempt/平台授权/41 个用例名与状态三平台一致。

## 云端验收结果（同源、同 attempt）

- 受测源码：**f8e765b15932b6b738f709bd03b48c4f0d6b0c4f**
- 工作流：`.github/workflows/reader-keyboard-actions.yml`，run **40130358865**，attempt 1，结论 success
- 作业：`keyboard actions (ubuntu-22.04)` = 120980574787、`keyboard actions (windows-2022)` = 120980574909、
  `keyboard actions (macos-14)` = 120980574974、`strict keyboard-actions evidence` = 120980924321，四项全部 success
- 每个平台 **41 项**具名结果（20 项安装后 C 消费者 + 7 项安装后 C++ 消费者 + 14 项原生 probe），全部 PASS
  或登记在案的 SKIP；三平台用例名集合完全一致
- 安装证明（每个平台各一份）：消费者 `CMakeCache.txt` 的 `EXReaderKeyboardActions_DIR` 指向
  `build/kbd-stage/lib/cmake/EXReaderKeyboardActions`，编译日志提到该前缀且**不含**源码 include 路径
- 工件（API 摘要，已由证据作业下载并重算字节数与 sha256，`strict keyboard-actions evidence` 通过）：

| 工件 | ID | 字节 | digest | 有效期 |
| --- | --- | --- | --- | --- |
| reader-keyboard-actions-Linux-40130358865-1 | 12574503984 | 122414 | sha256:fc2532e9e317c528126d8cb6574fcc5875af76233a8a6285cfb18c85e44781c3 | 2027-01-22T20:34:05Z |
| reader-keyboard-actions-Windows-40130358865-1 | 12574799025 | 90360 | sha256:f8ff2219862b5d281db19acb9fe5a3a68ea8ca22a20ec1b0ed5ee878c3b93b42 | 2027-01-22T20:34:05Z |
| reader-keyboard-actions-macOS-40130358865-1 | 12574184229 | 94528 | sha256:1ae073e39b050860028c13121ba774ebc4dfb8ca60f699c08053f502fe6c5f1c | 2027-01-22T20:34:05Z |
| reader-keyboard-actions-summary-40130358865-1 | 12574704001 | 1972 | sha256:112d263b72f76790c1111467f6e1144922692131ea001358085f8f8393e8794b | 2027-01-22T20:34:05Z |

受测消费者二进制（由各自报告记录，sha256 前缀）：Linux C `7dbb73c6` / C++ `fbd1fddb` / probe `42579945`；
Windows C `2c72e659` / C++ `1a0cb612` / probe `24901268`；macOS C `e2310aaa` / C++ `8504cafa` /
probe `bbe17659`（完整值见 `docs/validation/reader-keyboard-actions.json` 的 `platforms.*.binaries`）。

实际观测到的行为（摘自证据报告，非声明）：

- Linux：`reader-repeat-bounded` 真实通过（X 服务器对注入按键自动重复，动作数落在硬上限内）。
- Windows：`reader-repeat-bounded` 为 SKIP —— 该 runner 不对 `SendInput` 注入的按键产生自动重复
  （`page_actions=1`）；重复上限由 C 消费者 `repeat-policy` 与 probe 的三平台同名用例承担。
- macOS：`deactivate-cancels` 为 SKIP —— 托管 runner 不允许该进程成为活动应用，`NSApp deactivate`
  不产生取消；同一取消路径由 `focus-change-forgets-hold`（窗口所有权转移）在三平台真实验证。
  事件派发路径在 probe 详情里逐次记录（该 runner 上为 `window`，即 `NSWindow sendEvent:`）。

## 明确未覆盖

- **IME 真机组词**：托管 runner 上没有安装输入法（Linux 无输入法服务、Windows 无 IME、macOS 无
  输入法且无辅助功能授权）。`composing` 门限行为由 C 消费者的 `context-gating` 与 win32 的
  VK_PROCESSKEY 向量覆盖；probe 的 `ime-composing-passthrough` 三平台均登记为 SKIP（唯一"三平台都
  未 PASS"的用例，证据作业对此单独计数并接受）。
- **系统级自动重复**：Windows runner 不对注入按键产生自动重复，该平台 `reader-repeat-bounded` 登记为
  SKIP；上限本身由 C 消费者 `repeat-policy` 逐项验证，Linux/macOS 的真实重复路径分别通过 X 服务器
  自动重复与真实 `NSEvent.isARepeat` 覆盖。
- **应用失活门限**：macOS 托管 runner 上无法让进程成为活动应用，`deactivate-cancels` 登记为 SKIP；
  失活取消的宿主策略由 Linux 的 `FocusOut`、Windows 的 `WM_ACTIVATE` 与 C 消费者的
  `context-gating` 的 `INACTIVE` 分支验证。
- **Android 设备**：本包只提供 `reader_kbd_event_from_android` 数字向量，不授予真机结论。
- **宿主接线**：四套宿主的快捷键表与 UI 由 root 后续统一接线，本包不授予宿主/UI 结论
  （`host_ui_accepted=false`）。

## 原始失败（保留，不删除）

九次真实失败按时间保留在 `docs/validation/reader-keyboard-actions.json` 的 `retained_failures`，每次
都记录了当时的 source SHA、run、失败作业与**当时的具体原因**（工作流引号转义、libX11 未链接、MSVC
C4127、CMake 配置日志误判、C++ key-up 期望、GMainContext 无界排空、C 字符串转义、NSApplication 非活动
丢事件、Xvfb 无窗口管理器、GtkWindow 事件顺序、证据作业自检门）。没有删除断言、没有换语料、没有把
真实失败改判为预期拒绝。

## 复现

1. 检出 `codex/reader-keyboard-actions` 上受测源码 `f8e765b15932b6b738f709bd03b48c4f0d6b0c4f`
   （或之后的最终 HEAD：两者之间只有文档提交，源码/测试/工作流逐字相同）。
2. 打开 run 40130358865 attempt 1：四个作业与上述 ID 对应。
3. 下载任一平台工件，解包后核对 `keyboard-evidence/result.json`（`accepted`、`checks=41`、
   每项 `status`/`detail`）与 `keyboard-evidence/probe.log`（`STEP` 与 `PROBE` 行）。
4. 下载证据工件，按其 `result.json` 核对其余三个工件的 `id`/`size_in_bytes`/`digest`/`expires_at`
   与 `platforms.*.install_proof`。
