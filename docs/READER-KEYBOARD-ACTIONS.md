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

## 明确未覆盖

- **IME 真机组词**：托管 runner 上没有安装输入法（Linux 无输入法服务、Windows 无 IME、macOS 无
  输入法且无辅助功能授权）。`composing` 门限行为由 C 消费者的 `context-gating` 与 win32 的
  VK_PROCESSKEY 向量覆盖；probe 的 `ime-composing-passthrough` 逐平台登记为 SKIP。
- **系统级自动重复**：若某 runner 不对注入按键产生自动重复，`reader-repeat-bounded` 登记为 SKIP
  并写明原因；上限本身由 C 消费者的 `repeat-policy` 逐项验证。
- **Android 设备**：本包只提供 `reader_kbd_event_from_android` 数字向量，不授予真机结论。
- **宿主接线**：四套宿主的快捷键表与 UI 由 root 后续统一接线，本包不授予宿主/UI 结论。

## 复现

1. 检出 `codex/reader-keyboard-actions` 分支的目标 SHA（见 `docs/validation/reader-keyboard-actions.json`
   的 `source_sha`）。
2. 在该 run 的 Actions 页面查看 `keyboard actions (<runner>)` 三个作业与 `strict keyboard-actions evidence`。
3. 下载三个平台工件（名称 `reader-keyboard-actions-<Platform>-<run>-<attempt>`），核对
   `keyboard-evidence/result.json` 与 `keyboard-evidence/probe.log`；证据工件
   `reader-keyboard-actions-summary-<run>-<attempt>` 含 ZIP 摘要与身份校验结果。
