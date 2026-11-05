# HANDOFF-RESULT-S19 — 五模块进入实际宿主时的单 SDK/provider 链接闭包

**结论：accepted=false。** 三轮完整云端轮次已用完（另有两次中途取消），
本轮（第 3 轮）在 macOS 上真实链接出产品 DSO 与宿主可执行文件，但 Linux/Windows 的
DSO 链接失败，且驱动在 macOS 的第一个负例断言处中止，五条真实业务路径与
单 SDK/单 store 的运行期证据**均未产生**。失败原因已逐条定位到可直接执行的修法，
**但未应用、未验证**（改源码则“被测源码 == CI 跑过的源码”不再成立）。原样交回。

## 1. 身份

| 项 | 值 |
| --- | --- |
| 固定 seed | `d263ce5228838ac90c0a0dc13a5193d4a7739681` |
| 批准 SDK 候选（未改） | `edddc463c06ed5731195cdb8f06b2df6dff7699e`（3.41.0，ABI 1） |
| 分支 | `codex/reader-wave3-s19`（仅功能分支；未开 PR、未打 tag/Release、未动默认分支） |
| **受测源码 SHA** | **`1423a0f09f176793c6a0068e34b90e034ca72493`** |
| 最终 run / attempt | `40246747578` / `1` |
| 最终文档提交 | 见本文件所在提交（`[skip ci]`，不触发新功能测试；其 HEAD 在交回消息里给出） |
| 工件 | **无**（本 attempt 未上传任何 artifact；失败在 workspace 阶段） |

jobs（同一 run/attempt）：guard `121329803025` success；linux `121329834343` failure；
windows `121329834345` failure；macos `121329834472` failure；evidence skipped。

## 2. 交付内容（都在独占路径内）

| 路径 | 内容 |
| --- | --- |
| `tools/reader_host_feature_link.cmake` | 窄 CMake 模块：`exr_reader_host_feature_link_declare()` / `..._attach()`，含单 SDK/单 store/单模块来源与 provenance 复用、平台 rpath、六类混配拒绝 |
| `apps/reader/host-feature-link/` | 可安装的 host-link 包（1.0.0）：只装上述同一份模块 + Config，**不含**库/头/代码/第二个 provider |
| `tests/reader_wave3_s19/host/` | 真实产品 DSO（`features.cpp`：五模块真实业务路径 + 4 个 C 导出）与真实宿主可执行文件（`main.cpp`：运行时枚举模块、加载 DSO、比较 SDK 指针同一性） |
| `tests/reader_wave3_s19/run.py` | Actions 驱动：seed/SDK/所有权守卫、单前缀安装 13 个包、构建 DSO+程序、六个混配负例、五模块业务路径、符号表与加载器证据、result.json |
| `tests/reader_wave3_s19/{pe.py,verify.py}` | Windows PE 导出/导入解析（不依赖 dumpbin）；同 run 证据复算（源码/用例集/程序字节与摘要/跨平台用例一致/工件 size+digest+有效期） |
| `.github/workflows/reader-wave3-s19.yml` | guard + 三平台矩阵 + evidence（同 run 复核） |
| `docs/reader-wave3-s19/{README.md,validation.json}` | 消费说明、拒绝矩阵、本轮验证记录 |

未改：五包实现/Config、`apps/reader/desktop`、根 `CMakeLists.txt`、SDK `src/include/cmake/bindings`、
schema、`extras`、`examples`、旧测试与旧裁判（驱动与 workflow 每次在 Actions 里 `git diff --exit-code` 复查）。

## 3. 本轮真实通过的范围（不是推断）

- **守卫**：seed 祖先、SDK 树与 `edddc463` 逐字节相同、独占路径白名单、驱动语法检查 → success。
- **单前缀安装**：按 `reading-library` 预设 + `-DEXR_BUILD_SHARED_COMPAT=ON` 安装 SDK 3.41.0，
  再依次安装 13 个包（product catalog 0.1.0、webdav 0.2.0、revisions 0.3.0、reading-state 0.1.0、
  jump-history 0.1.0、sync 0.1.0、session 0.1.0、sync-view 0.1.0、annotation-import 0.1.0、
  annotation-export 0.1.0、font-library 0.1.0、original-export 0.1.0、host-feature-link 1.0.0），
  **三个平台全部成功**（macOS 打出 `PASS installed-five-reviewed-packages`）。
- **闭包声明/挂接**：`declare()` 通过（单 SDK 前缀、精确版本、单 catalog、复用已安装
  `_exr_sdk_target_provenance` 校验 `EXReader::exreader`），`attach(FEATURE_DSO)`/`attach(HOST_EXECUTABLE)`
  规则全部通过；`features.cpp`（同时使用五包公开头）**三平台编译通过**。
- **macOS 真实链接**：`libreader_host_features.dylib` 与 `reader-host-probe` 均链接成功
  （`PASS host-dso-and-executable-built-from-installed-packages`）。
- **混配拒绝（已观测 3/6）**：`negative-dso-static-sdk`（“a product DSO must not embed a second SDK
  implementation”）、`negative-two-feature-dso`、`negative-host-links-module` 三个负例被真实拒绝。

## 4. 保留的失败与根因（未抹除、未应用修法）

1. **Linux / 产品 DSO 链接失败**
   `/usr/bin/ld: libreader_annotation_import.a(annotation_import.cpp.o): relocation R_X86_64_TPOFF32
   against `_ZN12_GLOBAL__N_16activeE' can not be used when making a shared object; recompile with -fPIC`
   根因：五个可选包自身不设 `CMAKE_POSITION_INDEPENDENT_CODE`（只有 SDK 顶层设了），
   默认安装出的静态库带 TLS 静态量，无法进入共享对象。
   修法（未应用）：安装这些包时加 `-DCMAKE_POSITION_INDEPENDENT_CODE=ON`；不改任何源码/target/头文件。
2. **Windows / 产品 DSO 链接失败**
   `error LNK2005: exr_library_open / exr_document_open_memory / exr_anchor_create / exr_font_count /
   exr_version ... already defined in exreader.lib(exreader.dll)` → `fatal error LNK1169`。
   根因：MSVC 仍会把模块接口里 `EXReader::exr_core` 的真实静态依赖成员拉进来，与共享 SDK 的导入库冲突；
   而“删真实依赖/重贴标签”是被禁止的。
   修法（未应用）：Windows 上改走**静态单 SDK 闭包**（`SDK_LINK static`，SDK 只存在于 DSO 内，
   宿主可执行文件不再链 SDK）；ELF/Mach-O 上的共享 SDK 剖面保持现状（macOS 已验证可链接）。
3. **macOS / 负例断言误报**
   `AssertionError: ('negative-module-outside-prefix', 'resolved outside every declared install prefix', ...)`
   根因：CMake 把拒绝信息按 80 列换行（“resolved outside\nevery declared install prefix”），
   驱动的子串断言因此不匹配；拒绝本身是正确的。修法（未应用）：断言前把空白归一化。
   该误报同时中止了其余 3 个负例与全部业务路径。

## 5. 本轮之前的历史（原样保留）

| run | 源码 | 结果 | 原因 |
| --- | --- | --- | --- |
| 40245903358 | `f751e813` | cancelled | 排队阶段自查发现原件导出的目录串悬垂指针，先取消再改 |
| 40245998177 | `fa5f3cd9` | failure | CMake 把 helper 的模块表拍平成一个列表，`list(GET)` 在三平台全部报错 |
| 40246303666 | `e700b01b` | cancelled | 构建中确认证据校验器需按前缀匹配带版本号的 SDK 模块名，取消后重推 |
| 40246373859 | `c885289d` | failure | `features.cpp` 用了不存在的 `READER_ANNOTATION_IMPORT_OK`（真名 `READER_AI_OK`）+ MSVC 链接期 linkage 不一致 |

## 6. 未验证 / 不出结论

- 五模块的真实业务路径（字体导入+租约、原件导出字节比对、标注导出→导入往返、跳转历史落地/回看/解析/回退、
  真实 DAV 会话状态快照）**一次都没跑通**；没有任何 result.json、程序 hash、符号表或加载器证据。
- “一个 SDK 实现 / 一个产品 store provider”的运行期断言（`exr_version()` 指针同一性、`exr_` 符号缺席、
  加载模块数、导入表）**未产生**。
- 其余 3 个混配负例（module-outside-prefix / standalone-alongside-dso / private-second-store）未断言成功。
- Windows 静态单 SDK 剖面未构建；PIC 修正后 Linux 的 DSO 未验证。
- 无工件 ZIP，故无 size/SHA/有效期身份可报。
- 未涉及宿主 UI、真机、安装包、性能；未重跑 S14/S15/S16/S17 原矩阵（属各自包）。

## 7. 接入命令（给 C09/C10/C11/D15，按本轮已验证/未验证分段）

已验证可用的部分（macOS 实测链接通过、三平台编译通过）：

```cmake
find_package(EXReader 3.41.0 EXACT CONFIG REQUIRED COMPONENTS core library)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderHostFeatureLink 1.0.0 EXACT CONFIG REQUIRED)

exr_reader_host_feature_link_declare(host_features
  SDK_PREFIX "${EXR_SDK}" SDK_VERSION "3.41.0" SDK_LINK shared
  STORE_PREFIX "${EXR_STORE}" PACKAGE_PREFIXES ${EXR_MODULE_PREFIXES})

add_library(product_features SHARED features.cpp)   # 五模块归属者 + 唯一 store provider
exr_reader_host_feature_link_attach(product_features host_features ROLE FEATURE_DSO)

add_executable(product main.cpp)                    # 只链共享 SDK，不链模块与 catalog
exr_reader_host_feature_link_attach(product host_features ROLE HOST_EXECUTABLE HOST_OF product_features)
```

使用前必须补齐的两条（本轮实测得出，未在 CI 里验证）：

1. 若消费者是 DSO：安装五包时加 `-DCMAKE_POSITION_INDEPENDENT_CODE=ON`（Linux 必需，macOS 无影响）。
2. Windows：改用 `SDK_LINK static` 的静态单 SDK 闭包，宿主可执行文件不链 SDK；
   当前的 `SDK_LINK shared` 剖面在 Windows 会 `LNK2005/LNK1169`。

## 8. 边界声明

- 只写 `tools/reader_host_feature_link.cmake`、`apps/reader/host-feature-link/`、
  `tests/reader_wave3_s19/`、`.github/workflows/reader-wave3-s19.yml`、`docs/reader-wave3-s19/`、本文件。
- 本地只做源码阅读、Git 与后台进程管理；构建、编译、测试、夹具、工件下载/解析全部在 GitHub Actions。
- 未派子代理、未用 cpuse；未改冻结 SDK、原 guard 字节、其他包、根 CMake、schema、原七模块与旧预算。
- 未把缺失能力写成成功；seed 仍不是已验收 BASE，本包也未提升任何 BASE。
