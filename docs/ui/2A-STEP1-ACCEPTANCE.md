# 2a 第 1 步验收清单

对应 [HOST-AUDIT-20261104.md](HOST-AUDIT-20261104.md) §G5 第 1 步：独立的 D2D 外壳模块与构建接线，无可见变化。

- 代码基线：`origin/main` @ `26dac733`。下文行号指这一提交的 `examples/reader.c`。
- `shell_d2d.*` 尚不存在。§1 的命令已用存根文件在本机验证过语法和预期结果，模块写好后原样执行。
- 本文档写作时未改任何代码。
- **四节全部打勾才算第 1 步通过。**

## phase 判据是棘轮

phase 基线不是 0。第 1 步与第 6 步的 phase 判据是：**失败数 ≤ 2，且不新增失败；若出现第 3 个失败 → 本次验收不通过。** 基线值和来源见 §3.4，缺陷记录在 [issue #45](https://github.com/NoGod3524/EXReader/issues/45)。

## 1. 模块单独编译（不含 `reader.c`）

### 怎么做

在仓库根目录执行，MinGW 和 MSVC 都要跑：

```bash
g++ -std=c++17 -Wall -Wextra -Werror -c examples/windows/shell_d2d.cpp -o build/step1/shell_d2d.o
```

```bash
gcc -std=c11 -Wall -Wextra -Werror -x c -fsyntax-only examples/windows/shell_d2d.h
```

```bash
g++ -shared -Wl,--no-undefined build/step1/shell_d2d.o -ld2d1 -ldwrite -luser32 -lgdi32 -lole32 -o build/step1/shell_d2d_probe.dll
```

```bash
nm -u build/step1/shell_d2d.o
```

```bash
grep -nE '#include *"[^"]*(reader\.c|\.inc)"|exr_|host_state' examples/windows/shell_d2d.h examples/windows/shell_d2d.cpp
```

MSVC（Developer Command Prompt）：

```text
cl /nologo /c /std:c++17 /utf-8 /W4 /WX /MT examples\windows\shell_d2d.cpp /Fo:build\step1\shell_d2d.obj
```

### 怎么算过

- [ ] **C-1** `g++ -c` 退出码 0，标准输出和标准错误都为空。
- [ ] **C-2** 头文件按 C11 语法检查，退出码 0，输出为空（证明 `reader.c` 能以 C 引用它）。
- [ ] **C-3** `--no-undefined` 链接退出码 0。这一步证明模块没有任何指向 `reader.c` 的未解析符号。
- [ ] **C-4** `nm -u` 的输出里，匹配 `exr_`、`host_` 或单独符号 `g` 的行数为 0。
- [ ] **C-5** `grep` 无匹配（退出码 1）：模块不 include `reader.c` 或 `.inc`，也不引用 SDK 和宿主状态。
- [ ] **C-6** MSVC 退出码 0，输出只有源文件名 `shell_d2d.cpp`，无警告。
- [ ] **C-7** 交付包文件数和文件名与基线相同；`EXReader.exe` 新增的依赖只允许 `d2d1.dll`、`DWrite.dll`，这两个都是系统 DLL，不进包。

本机存根验证结果：编译、头文件、链接退出码都是 0，`nm -u` 只有 `D2D1CreateFactory`、`DWriteCreateFactory`。C-6 本机没有 `cl`，未验证，要在 CI 或装有 MSVC 的机器上跑。

## 2. `--self-test` 26 项

### 怎么做

```text
EXReader.exe --self-test <Reader.otf> <Sample.epub> <Sample.pdf> <report.json> <page.png>
```

参数必须恰好 5 个，否则进程返回 2（`:6024`）。`Sample.epub` 由 `tools/build_windows_host.py` 生成（`make_epub(..., 3, 16384, single_paragraph=True)`），`Sample.pdf` 复制自 `tests/fixtures/pdf-public.pdf`。

### 怎么算过

判据：**退出码 = 0 且报告 `checks` = 26，两者都要看。**

- [ ] 进程退出码 0。
- [ ] `report.json` 的 `passed` 为 `true`，`checks` **恰好等于 26**，`engine_version` 与 SDK 版本相同。
- [ ] 下面 26 项都成立。

`CHECK` 遇到第一个不成立的条件就跳到结束，所以 `checks` 少于 26 时，第一个失败项就是序号 `checks + 1`。

| 项 | 行 | 名称 | 判定条件 |
| --- | --- | --- | --- |
| S-01 | 6026 | 字体路径转换 | 字体路径转 UTF-8 成功，`name` 非空 |
| S-02 | 6027 | 打开字体 | `exr_font_open` 返回 `EXR_OK` |
| S-03 | 6030 | 打开 EPUB | `st_open_book(epub)` 返回 `EXR_OK` |
| S-04 | 6031 | EPUB 分页器存在 | `r` 和 `r->pager` 非空 |
| S-05 | 6032 | 渲染第 1 页 | `st_render(r, 0, &a)` 返回 `EXR_OK` |
| S-06 | 6033 | 页宽 | `a.bitmap.width == 720` |
| S-07 | 6034 | 页高 | `a.bitmap.height == 1040` |
| S-08 | 6035 | 通道数 | `a.bitmap.channels == 4` |
| S-09 | 6036 | 显示缓冲和页文本 | `a.dib` 非空，`a.text` 非空且首字符非 0 |
| S-10 | 6037 | 行跨度 | `a.bitmap.stride >= width * 4` |
| S-11 | 6039 | 输出路径转换 | PNG 路径转 UTF-8 成功 |
| S-12 | 6040 | 写 PNG | `exr_bitmap_write_png` 返回 `EXR_OK` |
| S-13 | 6041 | 渲染第 2 页 | `st_render(r, 1, &b)` 返回 `EXR_OK` |
| S-14 | 6042 | 第 2 页页码 | `b.page == 1` |
| S-15 | 6044 | 重新渲染第 1 页 | `st_render(r, 0, &again)` 返回 `EXR_OK` |
| S-16 | 6045 | 重渲染行跨度一致 | `a.bitmap.stride == again.bitmap.stride` |
| S-17 | 6046 | 重渲染像素一致 | `memcmp` 全部像素字节为 0 |
| S-18 | 6047 | 重渲染文本一致 | `wcscmp(a.text, again.text) == 0` |
| S-19 | 6051 | 关闭书后首帧仍有效 | 关闭书后 `a.bitmap.pixels` 非空，`a.text[0]` 非 0 |
| S-20 | 6053 | 打开 PDF | `st_open_book(pdf)` 返回 `EXR_OK` |
| S-21 | 6054 | 固定页文档存在 | `r` 和 `r->fixed` 非空 |
| S-22 | 6055 | 渲染 PDF 第 1 页 | `st_render(r, 0, &a)` 返回 `EXR_OK` |
| S-23 | 6056 | PDF 尺寸为正 | 宽和高都 > 0 |
| S-24 | 6057 | PDF 尺寸上限 | 宽和高都 ≤ 1440 |
| S-25 | 6058 | PDF 通道和缓冲 | `channels == 4`，`a.dib` 非空 |
| S-26 | 6060 | 打开报告文件 | `_wfopen(report)` 成功 |

### 第 27 个 `CHECK`：只看报告不能判过

源码共 27 个 `CHECK`，报告只写 26。

| 行 | 代码 | 语义 |
| --- | --- | --- |
| `:6063` | `int closed = fclose(report); ... CHECK(!closed);` | 关闭 `report.json` 成功，也就是报告内容已完整落盘 |

- 它排在 `:6061` 的 `fprintf` 之后，不写入报告里的 `checks`。
- 它失败时只体现在退出码上：退出码是 1，磁盘上的报告却可能写着 `passed: true`、`checks: 26`。所以只看报告不能判过。
- `tools/build_windows_host.py` 同时检查退出码和报告；手工验收也必须这样做。
- 本清单不改自检语义。如果认为它应当计入 `checks`，改代码前先报告：报告写在这个文件里，无法在关闭之前记录关闭结果，而且 `tools/check_windows_host.py` 要求 `checks` 等于 26。

自检用自己的 720×1040 配置（`st_open_book`，`:5945`），不走 `session_configure`，所以后面第 3 步改页面尺寸不应影响这 26 项。

**当前基线**：本地构建 `checks` = 26，退出码 0，`engine_version` 为 `3.42.0`。

## 3. phase-a / b / c

### 3.1 各跑什么

脚本在 `tests/windows_host/`，由宿主 `--drive` 在进程内逐步执行。不改脚本。

| Phase | 步数 | 截图 | 内容 | 动作构成 |
| --- | --- | --- | --- | --- |
| A | 120 | 5 | 导入和去重、翻页、字号、改窗口尺寸、选择和复制、流式与固定页标注增删改跳转、删书、不支持和损坏文件、取消导入、过期任务 | `check` 47，`state` 20，`next` 9，`import` 6，`snapshot` 5，其余 33 |
| B | 29 | 2 | 重启后恢复书架、页码和标注，固定页恢复，改字号 | `check` 14，`state` 4，`snapshot` 2，其余 9 |
| C | 9 | 1 | 改字号后再重启，检查字号、标注、恢复状态 | `check` 5，`wait_idle`、`state`、`snapshot`、`quit` 各 1 |
| **合计** | **158** | **8** | | |

三个 phase 共用同一个数据目录，必须按 A → B → C 顺序连续运行，中途不清数据。截图名是：

- A：`00-empty-shelf`、`01-epub-page1`、`02-resized`、`03-pdf-page1`、`04-stale-final`
- B：`10-restored`、`11-font-changed`
- C：`20-restored-after-font`

### 3.2 怎么做

官方跑法（`tools/check_windows_host.py` 会启动真实程序三次，并校验持久化、锚点恢复、取消和文件哈希）：

```text
python tools/build_windows_host.py --sdk stage --binary <EXReader.exe> --output build/step1-pkg
python tests/windows_host/make_fixtures.py --output build/step1-fixtures
python tools/check_windows_host.py --package build/step1-pkg/EXReader --output build/step1-ui --sdk stage --manifest build/step1-pkg/build.json --steps tests/windows_host --fixtures build/step1-fixtures --selftest-report build/step1-pkg/report.json --consumer-binary <消费者二进制>
```

运行时设环境变量 `EXREADER_HOST_ACCEPTANCE=1`。这个工具要求工作区已跟踪文件无改动，也就是必须在已提交状态下跑。

### 3.3 失败怎么计数，怎么算过

失败数的定义：

- 每个 `drive.log` 里 `^STEP\t<序号>\t<动作>\tFAIL` 的行数，三个 phase 相加。
- 宿主每次写 `FAIL` 就让 `g.drive_failures` 加 1（`drive_step_finish`），结束时写 `DONE\t...\tFAIL`，进程退出码为 1。
- 步数少于计划（A 120 / B 29 / C 9）算作失败，不按“没跑到”处理；官方工具同样拒绝截断的日志。

判据：**失败数 ≤ 2，且不新增失败；若出现第 3 个失败 → 本次验收不通过。**

“不新增”指失败步骤必须属于 §3.4 的已知集合 {A 第 115 步、B 第 5 步}。其他任何一步失败，即使总数 ≤ 2，也不通过。

- [ ] **P-1** phase A：`STEP` 120 行，FAIL 行只允许第 115 步。
- [ ] **P-2** phase B：`STEP` 29 行，FAIL 行只允许第 5 步。
- [ ] **P-3** phase C：`STEP` 9 行，FAIL 0 行，退出码 0。
- [ ] **P-4** 三个 phase 的 FAIL 合计 ≤ 2。
- [ ] **P-5** 8 张截图齐全。

**官方工具的结果不能直接用作判据。** 只要有 1 步失败，`check_windows_host.py` 的 `parse_log` 就会拒绝该 phase，退出码非 0，`passed` 为 `false`。所以棘轮期间以 `drive.log` 的计数为准，官方工具的退出码只作记录。基线归零后，把判据收紧回“退出码 0、`counts.passed` = 158”。

棘轮只能往下走：失败数一旦降低，新值就是新基线，不能回升。

### 3.4 基线

**基线值：失败数 2。**

| 来源 | 轮数 | A | B | C | 失败合计 |
| --- | --- | --- | --- | --- | --- |
| 本地 `26dac733`，MinGW，本地 SDK 3.42.0 | 2 | 119/120 | 28/29 | 9/9 | **2** |
| 本地 `4efd3366`（#43 之前），MinGW，同一 SDK | 2 | 119/120 | 28/29 | 9/9 | **2** |
| 官方 `wp13-windows.yml`，main `f22a7649`，MSVC | 1 | 120/120 | 29/29 | 9/9 | **0** |

官方基线是 [run 42071165411](https://github.com/NoGod3524/EXReader/actions/runs/42071165411)，只跑一次，不重试。这里用它而不是 `reader-desktop-sdk.yml`，因为后者第一步要求 SDK 与 `9854061` 相同，在 main 上必定失败。

**结果：CI 上是 0**（`summary.json`：`steps` 158、`passed` 158、`failed` 0，截图 8 张；自检 26 项通过）。按事先约定，本地 MinGW 环境有偏差，**官方基线以 CI 为准：0**。

两套基线分开用：

| 运行环境 | 基线 | 判据 |
| --- | --- | --- |
| 官方 CI（MSVC，`wp13-windows.yml`） | 0 | 失败数 0 |
| 本机 MinGW | 2（A 第 115 步、B 第 5 步） | 失败数 ≤ 2，且不新增失败；若出现第 3 个失败 → 本次验收不通过 |

同一 run 里另有两个与本步无关的门禁失败：H8 检查要求 SDK 树不变（`unchanged-SDK-tree/src`），worker 检查有 3 项超时。它们在 main 上原本就失败。

已知失败：

| 步骤 | 脚本期望 | 实际 |
| --- | --- | --- |
| A 第 115 步 | `check\|page\|3` | 第 4 页 |
| B 第 5 步 | `check\|page\|3` | 第 4 页 |

A 第 110 步重新打开书时，状态显示“进度锚点存在歧义，按已保存章内偏移回退恢复”，页码落在第 2 页，再翻两页到第 4 页。缺陷记录：[issue #45](https://github.com/NoGod3524/EXReader/issues/45)。

## 4. 开宏与不开宏的旧布局截图逐像素相同

### 4.1 出图工具

用现有的 `snapshot` 动作，不新增出图工具。它调用 `snapshot_png`，用 `PrintWindow(PW_RENDERFULLCONTENT)` 抓整个窗口（含标题栏），写成 `<evidence>/<名字>.png`。图片就是 §3.1 的 8 张。

### 4.2 怎么做

两个二进制除 `EXR_READER_WINDOWS_SHELL` 外完全同配置构建。

1. 在同一台机器、同一登录会话、同一缩放比例和系统主题下，把两个二进制依次放到**同一路径**运行。状态栏会显示路径，路径不同会造成像素差。
2. 每组运行前清空数据目录，并用相同路径。
3. 按 A → B → C 跑完，分别保存到 `off/` 和 `on/`。
4. **先做对照组**：不开宏的二进制跑两轮（`off1/`、`off2/`）。对照组不为 0 时，说明环境不稳定，开宏比对结果作废。
5. 比对解码后的像素，不比 PNG 文件哈希：

```python
from PIL import Image, ImageChops
a = Image.open(p).convert("RGBA")
b = Image.open(q).convert("RGBA")
assert a.size == b.size
assert ImageChops.difference(a, b).getbbox() is None
```

比对脚本放在 `examples/windows/acceptance/compare_shots.py`，随第 1 步一起提交。

### 4.3 怎么算过

**允许的像素差是 0，没有容差。**

- [ ] **V-1** 对照组 `off1` 对 `off2`：8 张都存在，尺寸相同，差异像素 0。
- [ ] **V-2** `off` 对 `on`：8 张都存在，尺寸相同，差异像素 0。
- [ ] **V-3** 比对脚本输出每张图的名称、尺寸和差异像素数，全文随证据保存。
- [ ] **V-4** 两组运行的缩放比例、系统主题和二进制 SHA-256 写入同一份记录。

只要有 1 张图有 1 个像素不同，就是不通过，不允许用“肉眼看不出”解释。

### 4.4 当前基线

本地构建（`26dac733`）跑两轮的对照组结果，差异像素全部为 0：

| 图 | 尺寸 | 差异像素 |
| --- | --- | --- |
| `00-empty-shelf` | 1180×900 | 0 |
| `01-epub-page1` | 1180×900 | 0 |
| `02-resized` | 1120×820 | 0 |
| `03-pdf-page1` | 1120×820 | 0 |
| `04-stale-final` | 1120×820 | 0 |
| `10-restored` | 1120×820 | 0 |
| `11-font-changed` | 1120×820 | 0 |
| `20-restored-after-font` | 1120×820 | 0 |

这说明“差异为 0”的判据在这台机器上可以达到。开宏后的结果要等第 1 步实现后才有。

**覆盖范围：** 这 8 张只覆盖脚本走到的状态，不代表所有界面状态。这里验证的是“旧布局无可见变化”，不验证新界面。

## 5. 第 1 步实测结果（2026-11-05）

分支 `codex/windows-shell-2a-step1-20261105`，基于 main `f22a7649`。本机 MinGW 加本地 SDK 3.42.0，`examples/` 构建（命令行补了 UIA 等库，见下）。

| 项 | 结果 |
| --- | --- |
| C-1 `g++ -c` | 退出码 0，输出 0 字节 |
| C-2 头文件按 C11 检查 | 退出码 0，输出 0 字节 |
| C-3 `--no-undefined` 链接 | 退出码 0，输出 0 字节 |
| C-4 `nm -u` 中 `exr_` / `host_` / `g` | 0 处；只有 `D2D1CreateFactory` 和 C++ 运行时符号 |
| C-5 `grep` | 无匹配（退出码 1） |
| C-6 MSVC `/W4 /WX` | 本机没有 `cl`；由 core 里的 Windows 构建验证（`exreader-shell-d2d` 在每个 Windows 构建中都会编译） |
| C-7 依赖 | 开宏后只新增 `d2d1.dll`（系统 DLL）；不开宏的交付包构建不变 |
| 自检，不开宏 / 开宏 | 退出码 0，`checks` 26 / 退出码 0，`checks` 26 |
| phase，不开宏（2 轮）/ 开宏 | 均为 A 120 步只第 115 步失败，B 29 步只第 5 步失败，C 9/9：失败 2，未新增 |
| 对照组 `off1` / `off2` | 8 张，差异像素均为 0 |
| `off1` / `on` | 8 张，差异像素均为 0 |

- 二进制 SHA-256：不开宏 `b675d3ef…`，开宏 `4532861d…`。
- 本机 MinGW 链接 `examples/` 的 reader 时，开宏和不开宏都缺 `UiaRaiseAutomationEvent` 等符号。原因是 `windows_accessibility.inc` 用 MSVC 专用的 `#pragma comment(lib)` 声明库，这是原有问题，与本步无关。本机验证时在命令行补了 `-luiautomationcore -loleacc -loleaut32 -lusp10 -lole32 -luuid`，仓库没有改。
- MinGW 开宏构建加了 `-static`，否则会额外依赖 `libstdc++-6.dll` 和 `libwinpthread-1.dll`。MSVC 用 `/MT`，不受影响。
