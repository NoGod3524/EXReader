# 依赖 / 许可 / 随包路径矩阵

这是**材料核对**，不是法律结论，也不声称项目整体合规。项目自身许可保持不变：[LICENSE](../../LICENSE)（MIT）；
第三方声明沿用 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)；登记表唯一事实源是
[tools/check_reading_licenses.py](../../tools/check_reading_licenses.py) 的 `COMPONENTS`（含固定来源、SHA-256 与开关）。
本包没有改动 `LICENSE`、`THIRD_PARTY_NOTICES.md`、`licenses/` 的任何字节。

“已核对”指某个事实被源码或 Actions 记录直接证明；其余一律标“未核对”。Actions 实测结果见
[EVIDENCE.md](EVIDENCE.md)（该文件由实际运行写入，缺失即表示尚无运行结果）。

## 1. 开关与六端构建所用配置（源码声明）

开关默认值来自 `CMakeLists.txt`；`reading-library` 预设见 [CMakePresets.json](../../CMakePresets.json)。

| 开关 | CMake 默认 | `reading-library` 预设（Windows、Linux 的 SDK） | Apple F06 构建（macOS / iPhone / iPad） | Android F06 构建 |
| --- | --- | --- | --- | --- |
| `EXR_ENABLE_PDF` | ON | ON | 默认 ON | ON |
| `EXR_ENABLE_PDF_CRYPTO`（Mbed TLS 子集） | ON | ON | 默认 ON | **OFF** |
| `EXR_ENABLE_PDF_JPX`（OpenJPEG） | ON | ON | 默认 ON | 默认 ON |
| `EXR_ENABLE_ICC`（LittleCMS + Argyll 配置） | ON | ON | 默认 ON | 默认 ON |
| `EXR_ENABLE_IMAGE_WEBP` / `TIFF` / `AVIF` | ON | ON | 默认 ON | **OFF** |
| `EXR_ENABLE_LIBRARY`（SQLite） | ON | ON（library 预设） | 默认 ON | ON |
| `EXR_ENABLE_AUDIO` / `EXR_ENABLE_MP3` | ON / ON | OFF / OFF | 默认 ON / ON | ON / 默认 ON |
| **`EXR_ENABLE_AAC`（FAAD2，GPL）** | **OFF** | **OFF** | **显式 OFF** | **显式 OFF** |

依据：Apple 取自 `tests/reader_f06_packages/build.py` 的 `apple()`（只显式写了 `EXR_ENABLE_AAC=OFF`、`EXR_BUILD_TESTS=OFF`、`EXR_BUILD_TOOLS=OFF`）；
Android 取自 `.github/workflows/android-composition-candidate.yml` 的 SDK configure 步骤；Windows 与 Linux 都执行 `cmake --preset reading-library`。
工作流会从每个已发布压缩包记录的真实 `CMakeCache.txt` 再核对一次，与上表不一致会写入 EVIDENCE.md。

## 2. 组件登记与随包许可文本

“随包路径”是 SDK 安装规则的目标（`share/exreader/licenses/...`）；桌面包把整个目录复制为包内 `licenses/`
（`tools/build_windows_host.py`、`build_linux_host.py`、`build_apple_host.py`）。

| 组件 | 版本（登记） | 许可（登记） | 启用条件 | 随包许可文本（`licenses/` 下） |
| --- | --- | --- | --- | --- |
| EXReader 自身 | 仓库 HEAD | MIT | 恒启用 | 包根 `LICENSE`（Windows 为 `LICENSE.txt`，Apple 为 `EXReader-LICENSE.txt`）+ `THIRD_PARTY_NOTICES.md` |
| FreeType | VER-2-15-0 | FTL（与 GPL-2.0-only 二选一，登记选 FTL） | 恒启用 | `freetype/FTL.TXT`、`freetype/LICENSE.TXT` |
| Expat | R_2_9_0 | MIT | 恒启用 | `expat/COPYING`、`expat/upstream-root/COPYING` |
| miniz | 3.1.2 | MIT | 恒启用 | `miniz/LICENSE` |
| stb_image | 2c980bb… | MIT 或公有领域（登记选 MIT） | 恒启用 | `stb/LICENSE` |
| SQLite | 3.54.0 | 公有领域 | `LIBRARY` 或 `BUILD_TEXT_INDEX` | `sqlite/sqlite-public-domain.txt` |
| OpenJPEG | 2.5.4 | BSD-2-Clause | `PDF` 且 `PDF_JPX` | `openjpeg/LICENSE` |
| LittleCMS | lcms2.19.1 | MIT | `ICC` | `lcms/LICENSE` |
| Argyll 默认 CMYK 配置 | 仓库数据 | 公有领域 | `ICC` | `default-cmyk-profile.txt` |
| Mbed TLS 子集 | 3.6.7 | Apache-2.0 或 GPL-2.0-or-later（登记选 Apache-2.0） | `PDF` 且 `PDF_CRYPTO` | `mbedtls/LICENSE` |
| libwebp | v1.5.0 | BSD-3-Clause | `IMAGE_WEBP` | `libwebp/COPYING`、`libwebp/PATENTS` |
| zlib | v1.3.1 | Zlib | `IMAGE_TIFF` | `zlib/LICENSE` |
| libtiff | v4.7.0 | libtiff（BSD 风格） | `IMAGE_TIFF` | `libtiff/LICENSE.md` |
| libaom | af3dc9a… | BSD-2-Clause 且 AOM Patent License 1.0 | `IMAGE_AVIF` | `libaom/LICENSE`、`libaom/PATENTS` |
| libavif | v1.2.0 | BSD-2-Clause | `IMAGE_AVIF` | `libavif/LICENSE` |
| minimp3 | ea99364… | CC0-1.0 | `AUDIO` 且 `MP3` | `minimp3/LICENSE` |
| **FAAD2** | 521d105… | **GPL-2.0-or-later** | `AUDIO` 且 `AAC`（默认关） | `faad2/COPYING`、`faad2/faad2-notice.txt` |
| Unicode 数据 | 17.0.0 / 3.2 | Unicode-3.0 | 恒启用 | `unicode/LICENSE.txt` |
| Adobe Glyph List | — | BSD-3-Clause | `PDF` | `pdf-font-data/adobe-glyph-list.txt` |
| PDF.js 编码/度量事实 | — | Apache-2.0 | `PDF` | `pdf-font-data/pdfjs.txt` |
| Noto Sans 测试字体（仅声明） | — | OFL-1.1 | 恒登记 | `wp7-fonts/noto-sans-test-fonts.txt` |
| 阅读字体 `Reader.otf` | 宿主字体缓存 | OFL（随 `OFL.txt` / `Noto-OFL.txt`） | 桌面与移动宿主 | 包内 `OFL.txt`（Apple 为 `Noto-OFL.txt`）；Android 在 APK `assets/OFL.txt` |

系统库（非随包，来自操作系统或发行版）：WebDAV/TLS/XML 用 `libcurl`+`libxml2`（Linux、macOS）或 `winhttp`+`xmllite`（Windows）；
凭据用 `libsecret`（Linux）、`advapi32`（Windows）、`Security` 框架（Apple）；GTK3 由 Linux 用户系统提供。依据：
[docs/READER-DISTRIBUTION-INVENTORY.md](../READER-DISTRIBUTION-INVENTORY.md) 第 3 节。该清单对应更早的 SDK 3.40 安装，
**不是当前 bd28d494 的清单**，也没有覆盖 Android/iOS 宿主与宿主字体。

## 3. 默认与可选依赖的发行条件（只列项目自己记录的内容）

- **FAAD2 AAC（可选，默认关）**：`CMakeLists.txt` 选项描述为“GPL-licensed”；`cmake/deps.cmake` 在启用时打印
  “FAAD2 is GPL-2.0-or-later: the linked binary cannot be distributed under MIT alone”；
  [licenses/faad2-notice.txt](../../licenses/faad2-notice.txt) 带有上游的 GPL 文本与“非 GPL 用法被禁止，商业授权须联系 Nero AG”的声明；
  `THIRD_PARTY_NOTICES.md` 的 “Optional AAC decoder” 节给出固定来源与范围。启用后的 SDK 安装规则会安装 `faad2/COPYING` 与 `faad2-notice.txt`。
  这里**不作**“能否在某种分发方式下使用”的判断；六端 F06 构建均为 `EXR_ENABLE_AAC=OFF`（上表），
  工作流会记录每个已发布压缩包里是否出现 `faad2/` 目录。若有人另行启用 AAC，需另走项目自己的许可评审。
- **minimp3**：CC0-1.0，默认 `EXR_ENABLE_MP3=ON`，但仅当 `EXR_ENABLE_AUDIO=ON` 才编入；`reading-library` 预设关闭音频。
  Apple F06 与 Android F06 构建**会**启用它（见第 1 节表），因此这两端的随包许可目录应含 `minimp3/LICENSE`。
- **Mbed TLS（PDF 加密）**：登记为 Apache-2.0 选项；Android F06 关闭。
- **AVIF/libaom 专利文件**：`libaom/PATENTS` 随 libaom 安装，登记的判断依据在 `docs/validation/reader-distribution-inventory.json`，本包不复述结论。
- **FreeType 双许可、SQLite 声明、PDF.js 数据、PostScript 操作名**：沿用 `THIRD_PARTY_NOTICES.md` 与既有登记，本包未重新评估。

## 4. 随包状态（静态读取打包脚本）

| 端 | 复制 LICENSE | 复制 THIRD_PARTY_NOTICES.md | 复制 SDK 的 `licenses/` 目录 | 来源脚本 |
| --- | --- | --- | --- | --- |
| Windows | 是（`LICENSE.txt`） | 是 | 是 | `tools/build_windows_host.py` |
| Linux | 是 | 是 | 是 | `tools/build_linux_host.py` |
| macOS | 是（`EXReader-LICENSE.txt`，在 `Resources`） | 是 | 是 | `tools/build_apple_host.py` |
| iPhone / iPad | 同 macOS（iPad 由 iPhone 载荷重新打包） | 是 | 是 | `tools/build_apple_host.py`、`identity.py package ipad` |
| Android | 是（压缩包根，APK 外） | 是（同） | **本分支前：否；本分支补丁：是（未在真实流水线验证）** | `tests/android_sdk342_package/run.py`（见 [PACKAGING-PATCH.md](PACKAGING-PATCH.md)） |

打补丁前，Android 脚本只复制两个根文件，没有复制 SDK 安装出的 `licenses/` 目录；其 SDK 构建启用了 FreeType、Expat、miniz、stb、
SQLite、OpenJPEG、LittleCMS、minimp3 等组件，这些组件的许可文本因此**不在** Android 压缩包里
（APK 内另有 `assets/OFL.txt`）。这是静态读取结论，Actions 对已发布压缩包的实测见 [EVIDENCE.md](EVIDENCE.md)。
补丁内容与未验证边界见 [PACKAGING-PATCH.md](PACKAGING-PATCH.md)。

## 5. 未核对 / 未验证

- 当前 bd28d494 源码上的六端新包：**没有**。F06 的 run 40678657371 打包的是 `8f8acf32`，其后 `annotation-export`、`annotation-import`、
  `original-import`、`reading-commands`、`reading-state`、`revisions`、`sync`、`store/native` 与 `extras/opds` 等模块已变化。
- 安装后文件与 SBOM 级别的依赖证据只存在于 SDK 3.40 的旧清单中，没有针对 3.42 重做。
- 所有许可文本内容与上游一致性：由 `tools/check_reading_licenses.py` 在 SDK 安装树上检查；本包只检查压缩包里**有没有**这些路径，
  并校验压缩包逐文件 SHA-256 与 manifest 一致，没有重复比较文本内容。
- 法律结论、再分发条件、专利、商标：均未判断。
