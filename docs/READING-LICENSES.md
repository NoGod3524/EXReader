# 阅读 preset 依赖与许可证材料清单（H5）

本文件给发布者一份可复现的第三方依赖与许可证材料清单，范围只限
`CMakePresets.json` 中的 `reading-core` 与 `reading-library` 两个 preset 在 Linux
（`ubuntu-22.04`）上的干净构建与安装 stage。

**这是“材料齐备检查”，不是法律判断。** 检查只回答：每个被下载、链接或安装的第三方项
是否已登记来源、固定版本与归档散列、启用条件，以及登记的许可证原文是否原样随包安装。
它不判断许可证是否相容、义务是否已履行，也不得据此宣称“全项目合规”。
历史版本的许可说明不在本次重写范围内。

## 复现方法

```bash
cmake --preset reading-core
cmake --build --preset reading-core
cmake --install build/reading-core
python3 tools/check_reading_licenses.py reading-core build/reading-core build/reading-core/stage build/reading-core/licenses.json
python3 tests/check_reading_licenses.py
```

`reading-library` 同理。云端由 `.github/workflows/reading-licenses.yml` 对两个 preset
各做一次干净配置、构建、安装、检查与自检，并把 `licenses.json`、`CMakeCache.txt`、
`exr-modules.json`、安装后的 `share/exreader/`、根目录 `LICENSE` / `THIRD_PARTY_NOTICES.md`
与 `EXReaderDependencies.cmake` 作为工件保存。云端记录见
[证据目录](validation/reading-h5-licenses/README.md)。

清单在 `tools/check_reading_licenses.py` 的 `COMPONENTS` 中，检查器只复用仓库现有的
`tools/check_reading_profile.py` 散列函数，不引入扫描服务。它从以下实际产物取证：

| 依据 | 判定 |
| --- | --- |
| `CMakeCache.txt` 的 `EXR_*` 开关 | 必须与 preset 解析结果一致；音频、MP3、AAC 必须为 OFF |
| `build/exr-modules.json` 的实际层 | 不得含 `audio`；`library` 层与 `EXR_ENABLE_LIBRARY` 一致 |
| `build/_deps/*-src` | 每个实际下载的依赖都须登记；禁用的依赖不得下载 |
| `stage/lib/exreader/*exr_vendor_*` 与 `EXReaderDependencies.cmake` | 两者一致；每个链接归档须属于已登记且已启用的组件 |
| `stage/share/exreader/licenses/**` | 登记文件存在、非空、与原始来源逐字节相同、与清单固定 SHA-256 相同；未登记文件即失败 |
| `cmake/deps.cmake`、`CMakeLists.txt` | 清单的 URL / 归档散列与固定依赖一致；每个登记文件有对应安装规则 |
| 上游源码顶层 `LICENSE*`、`COPYING*`、`NOTICE*`、`PATENTS*`、`COPYRIGHT*` | 未随包安装者列为“待处理”，不自动判为失败或通过 |

失败项使检查返回非零；“待处理”项单独列出，需要主代理或发布者决定。

## 组件清单

“链接”列为实际 stage 中的私有静态归档（`lib/exreader/libexr_vendor_<名>.a`）。
许可证散列为安装文件的 SHA-256，与上游原文一致，云端两个 preset 观测值相同。
许可证名称照录 `THIRD_PARTY_NOTICES.md` 的声明，仅作登记，不是法律结论。

| 组件 | 固定来源 / 版本 | 归档 SHA-256 | 启用条件 | 链接 | 许可证原文 → 安装路径（`share/exreader/licenses/` 下） | 原文 SHA-256 | core | library |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FreeType | freetype/freetype `VER-2-15-0` | `87c7f1f8…cdcac4fb8` | 总是 | `freetype` | `docs/FTL.TXT` → `freetype/FTL.TXT`；`LICENSE.TXT` → `freetype/LICENSE.TXT` | `5a5ee54c…02d02967f`；`bd36c8b4…64fd2d3b` | 是 | 是 |
| Expat | libexpat/libexpat `R_2_9_0` | `6e8ce7b5…0700cec27` | 总是 | `expat` | `expat/COPYING` → `expat/COPYING` | `31b15de8…39b25e87` | 是 | 是 |
| miniz | richgel999/miniz `3.1.2` | `98468f89…20e2e9fb` | 总是 | `miniz` | `LICENSE` → `miniz/LICENSE` | `0115478d…a01646b3` | 是 | 是 |
| stb_image | nothings/stb `2c980bb5…` | `9a955b1b…ba515` | 总是 | 头文件编入 `exr_graphics`（构建目录私有补丁副本） | `LICENSE` → `stb/LICENSE` | `bebfe904…6cff63` | 是 | 是 |
| libwebp | webmproject/libwebp `v1.5.0` | `668c9aba…0f37` | `EXR_ENABLE_IMAGE_WEBP` | `webp`、`webpdemux`、`sharpyuv` | `COPYING` → `libwebp/COPYING` | `5aec868f…e13acf` | 是 | 是 |
| zlib | madler/zlib `v1.3.1` | `17e88863…14d05c` | `EXR_ENABLE_IMAGE_TIFF` | `zlibstatic` | `LICENSE` → `zlib/LICENSE`，另一份 → `libtiff/LICENSE` | `845efc77…95753243` | 是 | 是 |
| libtiff | libsdl-org/libtiff `v4.7.0` | `8f568a0d…111e16` | `EXR_ENABLE_IMAGE_TIFF` | `tiff` | `LICENSE.md` → `libtiff/LICENSE.md` | `0780558a…e380d` | 是 | 是 |
| libaom | arthenica/libaom `af3dc9aa…`（上游 `CHANGELOG` 实测 3.15.2） | `a606215e…baa62a` | `EXR_ENABLE_IMAGE_AVIF` | `aom`（仅解码器） | `LICENSE` → `libaom/LICENSE`；`PATENTS` → `libaom/PATENTS` | `4764a286…de7f2`；`661fb8e5…96e61` | 是 | 是 |
| libavif | AOMediaCodec/libavif `v1.2.0` | `2182f490…7d8c` | `EXR_ENABLE_IMAGE_AVIF` | `avif` | `LICENSE` → `libavif/LICENSE` | `165abf92…8216f9` | 是 | 是 |
| Mbed TLS 加密子集 | Mbed-TLS/mbedtls `mbedtls-3.6.7` | `807f0a1c…055fcc` | `EXR_ENABLE_PDF` 且 `EXR_ENABLE_PDF_CRYPTO` | `exr_crypto`（7 个上游源文件）；ARC4 改编自 2.28.10，位于 `src/pdf_crypto.c` | `LICENSE` → `mbedtls/LICENSE` | `9b405ef4…2ad09b` | 是 | 是 |
| LittleCMS | mm2/Little-CMS `lcms2.19.1` | `267705e2…a709` | `EXR_ENABLE_ICC` | `exr_lcms` | `LICENSE` → `lcms/LICENSE` | `6dbd6043…484d31` | 是 | 是 |
| SQLite | sqlite.org 3.54.0 amalgamation | `68e913b0…5aa4d` | `EXR_ENABLE_LIBRARY` 或 `EXR_BUILD_TEXT_INDEX` | `exr_sqlite` | 无文件；检查 `sqlite3.c` 头部公有领域声明与 notices 行 | — | 否 | 是 |
| minimp3 | lieff/minimp3 `ea99364f…` | `5628166e…768f34` | `EXR_ENABLE_AUDIO` 且 `EXR_ENABLE_MP3` | — | `LICENSE` → `minimp3/LICENSE`（未构建，未核对） | 未固定 | 否 | 否 |
| FAAD2 | knik0/faad2 `521d1059…` | `9284bd9c…dfd8` | `EXR_ENABLE_AUDIO` 且 `EXR_ENABLE_AAC` | — | `COPYING`、仓库 `licenses/faad2-notice.txt` → `faad2/`（未构建，未核对） | 未固定 | 否 | 否 |
| Unicode 数据派生表 | UCD 17.0.0 与 3.2（各生成器固定输入散列） | — | 总是 | 生成的 C 表 | 仓库 `tests/fixtures/unicode/LICENSE.txt` → `unicode/LICENSE.txt` | `e7a93b00…bc53d96` | 是 | 是 |
| Argyll 默认 CMYK 配置文件 | 仓库 `src/profiles/default_cmyk.icc.zlib`（`20f63c91…53b2`） | — | `EXR_ENABLE_ICC` | 内嵌生成头 | 仓库 `licenses/default-cmyk-profile.txt` → `default-cmyk-profile.txt` | `45d3e9b1…80e1da` | 是 | 是 |
| Adobe Glyph List | adobe-type-tools/agl-aglfn `4036a9ca…` | — | 数据用于 `EXR_ENABLE_PDF`；文件总是安装 | `src/pdf_font_data.h` | 仓库 `licenses/adobe-glyph-list.txt` → `pdf-font-data/adobe-glyph-list.txt` | `c85f2b0d…6f3aa7` | 是 | 是 |
| PDF.js 编码与度量事实 | mozilla/pdf.js `81525fd4…` | — | 同上 | `src/pdf_font_data.h` | 仓库 `licenses/pdfjs.txt` → `pdf-font-data/pdfjs.txt` | `8d1fb642…15ca53` | 是 | 是 |
| PostScript 计算器操作名 | PDF 32000-1 表 42 | — | `EXR_ENABLE_PDF` | `src/pdf_calculator.c` | 仅 `THIRD_PARTY_NOTICES.md` 段落 | — | 是 | 是 |
| Noto Sans 测试字体（仅声明） | `tests/fixtures/wp7` | — | 总是安装声明；字体不安装 | 无 | 仓库 `licenses/noto-sans-test-fonts.txt` → `wp7-fonts/noto-sans-test-fonts.txt`；stage 中不得出现 `Noto*.ttf/otf/ttc` | `754f0e22…de70` | 是 | 是 |

表中散列只截取首尾便于阅读；完整值以 `cmake/deps.cmake` 和检查器清单为准。

根目录与 `share/exreader/` 下的 `LICENSE`、`THIRD_PARTY_NOTICES.md` 是 EXReader 自身材料，
检查器要求它们存在、非空且与同一提交的仓库文件逐字节相同，不在清单中固定散列，
以免每次正常修改 notices 都要改检查器。

## 源码许可证、链接组件与可选功能

- **仓库源码许可证**：EXReader 自身 C 代码为 MIT（根目录 `LICENSE`）。这只说明仓库代码，
  不代表链接产物中第三方部分的许可证。
- **实际链接组件**：以云端 stage 为准。`reading-core` 链接 12 个私有归档：
  `aom avif expat exr_crypto exr_lcms freetype miniz sharpyuv tiff webp webpdemux zlibstatic`，
  另有头文件形式编入的 stb_image；`reading-library` 额外链接 `exr_sqlite`。
- **可选功能**：两个 preset 的 `EXR_ENABLE_AUDIO`、`EXR_ENABLE_MP3`、`EXR_ENABLE_AAC`
  均为 OFF，实际构建层无 `audio`，`_deps` 中没有 `minimp3`、`faad2`，stage 中也没有它们的
  归档或许可证目录。因此 `THIRD_PARTY_NOTICES.md` 中“启用 FAAD2 后链接产物受 GPL 约束”的
  说明只适用于另行打开 `EXR_ENABLE_AAC` 的音频构建，**不适用于这两个阅读 preset 的产物**；
  反过来，本清单也不对音频构建作任何结论，minimp3/FAAD2 许可证文件未经本次构建核对。
- PDF 编辑、文本索引、共享兼容库、JNI、工具与测试在两个 preset 中均关闭，未纳入本清单。

## 未解决项（待处理，交主代理）

以下项由云端检查器逐项列出或由本次核对发现。本包不修改共享安装规则，也不手工复制文件掩盖。

1. **libwebp `PATENTS` 未随包安装。** 上游 v1.5.0 顶层有 `PATENTS`
   （SHA-256 `cc3273e0694ea5896145e0677699b53471b03ea43021ddc50e7923fbb9f5023c`），
   当前只安装 `COPYING`；同类的 libaom 已安装 `PATENTS`。建议在
   `CMakeLists.txt` 第 974 行把 `${libwebp_SOURCE_DIR}/PATENTS` 加入
   `share/exreader/licenses/libwebp`，随后在清单登记并固定散列。
2. **Expat 有两份不同的 `COPYING`。** 安装的是 `expat/COPYING`（版权年份 2001-2025）；
   仓库顶层 `COPYING`（SHA-256 `73cc92f80889ab23c7287b1a11dd50fdec190c3f26ebe5938c579043817d651e`）
   为同一 MIT 文本，但年份为 2001-2026。是否改装或并装由主代理决定。
3. **SQLite 无随包许可证文件**（仅 `reading-library`）。上游 amalgamation 不含许可证文件，
   公有领域声明只在 `sqlite3.c` 头部与 `THIRD_PARTY_NOTICES.md` 一行中；
   `share/exreader/licenses/` 下没有 SQLite 条目。是否补充说明文件由主代理决定。
4. **zlib 许可证被重复复制到 `licenses/libtiff/LICENSE`。** 来源是
   `CMakeLists.txt` 第 977 行把 `${zlib_SOURCE_DIR}/LICENSE` 与 libtiff 的 `LICENSE.md`
   同装一处；第 978 行已另装到 `licenses/zlib/LICENSE`。文件名易被误读为 libtiff 许可证，
   建议从第 977 行移除 zlib 文件；移除后同步删除清单中的第二个 zlib 条目。
5. **覆盖范围限制。** 只覆盖 Linux 静态 SDK；Windows（`.lib`）、macOS、Android 与原生宿主包
   （如 Noto Sans CJK 字体）未在本次运行。Apache-2.0 来源（Mbed TLS、PDF.js 数据）只核对了
   已登记与上游顶层文件，PDF.js 不在构建时下载，其上游 `NOTICE` 情况未由本工具核对。
