# SDK 五端构建一致性（S5）

**状态：PENDING — 正式五端产物与三端运行结果尚未收齐。** 本稿把已有测量与待测项分开；下面的历史数字不能替代本轮验收结果。

本轮来源是 [draft PR #108](https://github.com/NoGod3524/EXReader/pull/108) 自动触发的 [Native C engine run 42653099549](https://github.com/NoGod3524/EXReader/actions/runs/42653099549)。待收集产物的实际 checkout 为 PR merge commit `2325b63cbf4068fba7ae2761ad10678b0274bab6`，PR head 为 `30595c21`。构建清单记录实际 checkout，不用 head SHA 代替。首轮运行暴露 expat 版本头允许 `#  define` 空白的问题；版本提取器已修正，并以四个真实依赖头验证。

统一导出还暴露了两个白盒测试的链接问题：测试程序和 SDK 动态库各自包含 SQLite，隐藏依赖符号后不再通过 ELF interposition 共用同一实例。SQLite 的 POSIX inode 锁及延迟关闭表必须在同一进程共享；两份实例使锁冲突与 trigger 注入测试失效。仅将这两个测试链接到静态 SDK 组件，原断言全部保留；Windows/Linux 定向测试均 2/2 通过。见 [失败记录](../../evidence/s5/ci-sqlite-link-failure.txt)、[Linux 修复验证及 ldd](../../evidence/s5/smoke/linux-sqlite-focused-retry.txt)、[Windows 验证](../../evidence/s5/windows-sqlite-ctest.txt)。正式 cohort 统一使用修复后的 run。

## 构建清单汇总

| 平台 / 主产物架构 | 源码 commit / SDK 输入 SHA256 | 编译器 / CMake | Release 选项 / PIC | 产物字节数 / SHA256 | 实测导出数 |
|---|---|---|---|---|---|
| Windows / x86_64 | PENDING | PENDING | PENDING | PENDING | PENDING |
| Linux / x86_64 | PENDING | PENDING | PENDING | PENDING | PENDING |
| macOS / arm64 | PENDING | PENDING | PENDING | PENDING | PENDING |
| Android / arm64-v8a | PENDING | PENDING | PENDING | PENDING | PENDING |
| iOS / arm64 device | PENDING | PENDING | PENDING | PENDING | PENDING |

清单目标文件为 `build-manifest-windows.json`、`build-manifest-linux.json`、`build-manifest-macos.json`、`build-manifest-android.json`、`build-manifest-ios.json`。Android 模拟器另使用同源 x86_64 构建，其清单为 `build-manifest-android-x86_64.json`；它与主表 ARM64 分发库分别保留 SHA256，不互相代替。

[manifest.py](../../tools/crossbuild/manifest.py) 在配置时保存源码快照，安装时重新核对源码并读取实际安装库。字段包括：

- `source.commit`、Git tree、工作区改动状态、逐文件摘要及 `sdk_input_sha256`。SDK 输入覆盖 `CMakeLists.txt`、`cmake/`、`include/`、`src/` 和 `tools/layers.json`。
- 编译器 ID/版本、CMake 版本/生成器、Release 全局编译选项、PIC、全部 `EXR_BUILD_*`/`EXR_ENABLE_*` 配置及每层展开后的宏和编译选项。
- expat、FreeType、miniz、zlib 的实际版本头/文件摘要、声明的源码包 SHA256，以及实际解包目录摘要。依赖配置生成的文件可能使目录摘要不同；不能把源码包 pin 冒充实际覆盖目录的身份。
- 安装库 SHA256、字节数、文件格式、架构与逐名导出清单。静态 archive 的全局定义不当作动态导出。

当前声明的依赖 pin 为 expat **2.9.0**、FreeType **2.15.0**、miniz **3.1.2**、zlib **1.3.1**，见 [deps.cmake](../../cmake/deps.cmake)。五端实际依赖版本与关键宏一致性：**PENDING**。

## 符号逐名对比

当前全部公共头声明 **427** 个 `EXR_API` 函数。这是预期契约数，正式五端实测结果仍为 **PENDING**。

[modules.cmake](../../cmake/modules.cmake) 从启用组件的公共头生成同一份 `public-symbols.txt`，分别生成 Windows `.def`、ELF anonymous version script、Mach-O `exported_symbols_list`。导出文件加入 `LINK_DEPENDS`，公共头变化会触发重新配置和重新链接。静态组件保留内部定义供静态链接。

对比范围为每个动态库的全部命名导出，包括非 `exr_` 名字。Mach-O 只去掉一个 C ABI 前导下划线；PE/ELF 名字不改。每个 fat slice 单独检查，不通过合并多个架构掩盖缺失。正式报告 `symbols-current.json`：**PENDING**。

### 历史产物实测

[symbols-legacy.json](symbols-legacy.json) 保存五端完整名字、共有名字以及 **2411 条逐名差异**，每条都有 `present_on`、`absent_on`、`reason`。[输入与来源](symbols-legacy-inputs.json) 记录了实际文件位置和身份限制。

| 平台 | 全部导出 | 五端共有 | 超出共有集合 | 仅该平台拥有 |
|---|---:|---:|---:|---:|
| Windows | 389 | 389 | 0 | 0 |
| Linux | 2799 | 389 | 2410 | 0 |
| macOS | 2799 | 389 | 2410 | 0 |
| Android | 2800 | 389 | 2411 | 1 |
| iOS | 2799 | 389 | 2410 | 0 |

唯一的平台独有名字是 Android 的 **`__emutls_get_address`**，来自 NDK compiler-rt 的 emulated TLS helper。另 **2410 个**内部/第三方名字同时出现在四个非 Windows 平台，不能称为某一平台独有；例如 `exr_add_block`、`exr_pdf_open`、`FT_Activate_Size`。全部 2410 个名字逐条见上述 JSON 的 `differences`，没有只比较名称数量。

历史 Linux/macOS/iOS 符号集合相同，Windows 与它们不同。Apple 的解析结果已与 LLVM 的真实 exports trie 独立核对：macOS/iOS 均 **2799**，证据为 [macOS exports trie](symbols-macos-legacy-exports-trie.txt) 和 [iOS exports trie](symbols-ios-legacy-exports-trie.txt)。

## 同程序行为冒烟

三端都编译并执行 [同一个 C probe](../../tools/platforms/probe.c)。使用同一 EPUB、同一显式字体文件、同一搜索词 `deliveryneedle`，字体大小 18、页面 360×480、页边距 24、行高 1.5、段距 8。三端必须记录相同的书和字体 SHA256。`exr_publication_search_all` 验证完整的 **1000** 次预期命中，不把“找到第一个命中”当作命中数一致。

渲染第 1 页（API 页号 0）后，按行写出 RGBA，有效像素之外的 stride padding 不进入 SHA256；PNG 摘要单独保留。[最终三端结果](smoke-cross-platform.json) 已通过：每张图 **691200 字节、20543 个有墨像素**。

| 运行环境 | 页数 | 搜索命中 | 第 1 页 RGBA SHA256 |
|---|---:|---:|---|
| Windows 11 / CI MSVC DLL | 215 | 1000 | `c1a085e1c0292c666fd6fdf4d4001254c1171ca5584e5c636d18e819c128c3ef` |
| Linux Debian 12 / QEMU / CI GCC 库 | 215 | 1000 | `c1a085e1c0292c666fd6fdf4d4001254c1171ca5584e5c636d18e819c128c3ef` |
| Android 11 API 30 x86_64 模拟器 | 215 | 1000 | `c1a085e1c0292c666fd6fdf4d4001254c1171ca5584e5c636d18e819c128c3ef` |
| 三端一致 | **是** | **是** | **是** |

三端未观察到像素差异。输入字体固定为 Noto Sans CJK SC Regular（SHA256 `2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b`），EPUB 为 `9d7c41ce3173ce1e844d82f995de8aab98bc25a456b0f5a01da7a0e9cc86342c`。代码中 [fonts.c](../../src/fonts.c) 明确用 `FT_Set_Char_Size(...,72,72)`，普通轮廓字形在 [raster.c](../../src/raster.c) 使用 `FT_LOAD_DEFAULT` / `FT_RENDER_MODE_NORMAL`。同一字体、FreeType 版本、固定 72 DPI 和布局控制了这次冒烟的渲染条件；宿主桌面缩放比例没有进入这些参数。

[单变量字体对照](smoke-font-control.json) 使用同一 Windows MSVC 库、同一书和布局，仅将字体换为 Arial：仍为 **215 页、1000 命中**，但 **31997 个像素、95991 个 RGB 通道**改变，首字基线由 **45 变为 44**，RGBA SHA256 变为 `3448ab252cb33cbc799e4f914ed4ee4f857a26ca77f2fd91c369ede7d9ba4f35`。这项差异来自字体字形及度量的变化，DPI、SDK、FreeType 和操作系统保持固定。

## 已知不一致与原因

| 已观察的不一致 | 原因与证据 | 本轮处理 |
|---|---|---|
| 历史 Windows 比 Linux/macOS/iOS 少导出 2410 个名字 | 原实现只有 Windows 使用 `.def`；其他格式把 SDK 内部定义和静态链接的依赖定义暴露为动态符号。[完整逐名证据](symbols-legacy.json) | 统一按公共头控制三种格式出口；待正式五端核验 |
| 历史 Android 比 Linux/macOS/iOS 多 `__emutls_get_address` | NDK compiler-rt 的 TLS helper 被原无限制 ELF 链接导出；它不是公共 SDK API | 新 ELF version script 将其局部化；待 Android 正式产物核验 |
| 历史五端的构建 commit 身份记录不等价 | 非 Windows artifact 原记录的是 PR head `bd15cddb`，实际 CI checkout 是 merge `65b663a4428d14467865e772ac5702c970ae4a50`；Windows 则复用了本地注释功能构建，没有原子构建 commit。旧 source-tree 校验不能补造一次构建记录。[来源说明](symbols-legacy-inputs.json)、[旧 provenance](../../evidence/platforms-20261108/provenance.json) | 本轮配置快照与安装时复核绑定实际 checkout |
| 平台文件格式、架构和系统链接库不同 | Windows 用 PE/x86_64 与 winmm；Linux 用 ELF/x86_64 与 dl；Apple 用 Mach-O/arm64 与 AudioToolbox；Android 用 ELF/arm64 与 OpenSLES。后端由 [modules.cmake](../../cmake/modules.cmake) 显式选择 | 记录格式/架构/原始选项；比较相同 API 与行为，不要求五端二进制 SHA 相同 |
| 历史一次渲染回归的字体输入 SHA256 不同 | [原日志](../../evidence/platforms-20261108/realbooks-font-mismatch.txt) 明确给出 `incompatible_conditions: [font_sha256]`，比较器拒绝把它当作同条件回归 | 正式冒烟固定同一字体字节并核验 SHA；不把这个输入差异误报为平台 hinting 差异 |
| 字体替换时像素不一致，页数和搜索仍一致 | 本轮单变量对照仅从 Noto Sans CJK 换为 Arial，31997 像素改变，首字基线 45→44。[实测结果](smoke-font-control.json) | 字体按字节固定；使用库内固定 72 DPI |
| Android x86_64 的 expat 目录摘要与 CI 不同 | Windows 解包缺失 `README.md → expat/README.md` 符号链接；231 个普通文件均与原源码包逐字节相同，补入 README 摘要后完全复现 CI 目录摘要。[核对结果](../../evidence/s5/expat-source-tree-difference.json) | 如实保留不同目录摘要，确认差别不涉及编译源码 |

编译器和原始旗标预期随目标 ABI 不同：MSVC 的优化/运行库设置与 GCC/Clang 的 `-O3`/`-fPIC` 不是相同字符串。本轮验收比较同一 Release 意图、同一 SDK feature 和实际 `EXR_*` 宏，同时保留完整原始旗标供审查；具体版本与实际值以五端 manifest 为准，当前 **PENDING**。

## 最终验收命令

```sh
python tools/crossbuild/test_check_evidence.py
python tools/crossbuild/check_evidence.py --manifests docs/validation --symbols docs/validation/symbols-current.json --smoke docs/validation/smoke-cross-platform.json --android-runtime-manifest docs/validation/build-manifest-android-x86_64.json --output docs/validation/cross-platform-check.json
```

该检查把实际二进制符号报告的 SHA256/大小绑定到 manifest，并将三端运行库 SHA256 绑定到对应 manifest；同时要求五端实际 commit、SDK 输入、feature、依赖版本、427 个公共名字一致。冒烟页数或搜索不一致直接失败；像素不同必须保留真实布尔结论和原因。正式 `cross-platform-check.json`：**PENDING**。
