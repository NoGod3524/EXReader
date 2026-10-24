# G09：产品依赖、许可证与离线分发清单

固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-distribution-inventory`。
本文件是 reading 配置的离线分发材料：实际安装了什么、每个文件多大、散列与版本是什么、
真正链接了哪些静态归档、运行时导入哪些系统库、许可证原文从哪里来、notice 出自哪一段。
范围只到"桌面三平台 × 两个 reading preset 的实际安装结果"，不含移动打包与发布动作。

**两个出口分开记录：**

| 出口 | 结果 | 依据 |
| --- | --- | --- |
| 生成材料（清单 + 依赖 + 许可材料 + SBOM） | 通过 | run [40081161966](https://github.com/NoGod3524/EXReader/actions/runs/40081161966) attempt 1，8 作业全部成功，六份工件同源、非空、未过期、digest 与上传日志一致 |
| 发布就绪 | **未授予** | 96 处已安装文件仍携带构建机绝对路径（第 8 节）。这些文件的修复落在共享文档、上游安装规则与受保护构建配置里，不由本包改动 |

授予范围：六份桌面安装的逐文件清单/散列、真实静态与动态依赖、登记许可证原文与 notice 来源、
两份标准 SBOM，以及"未启用项确实没有混入"的实测。不含 Android/iOS/Apple 宿主打包、宿主字体、
签名/公证、tag/Release/商店发布，也不含法律结论。

## 1. 受测身份与云端出口

| 项目 | 值 |
| --- | --- |
| 受测源码 | `f3b5c8f65d6a1d7db51364b897f81a995ce37c67` |
| 实现起点（祖先约束） | `f43baf9182d75907c0cb5d6f77048f27bca8c950` |
| 冻结 SDK 保护树 | `9854061be331fe603a1822d9b2b36ee357154927`（与受测源码逐字节相同） |
| 产品 schema | `apps/reader/store/001_catalog.sql` 与实现起点相同 |
| 工作流 | `.github/workflows/reader-distribution-inventory.yml` |
| run / attempt | [40081161966](https://github.com/NoGod3524/EXReader/actions/runs/40081161966) / 1，success |
| 作业 | protocol `120834840566`、linux-core `120834897186`、linux-library `120834897219`、windows-core `120834897253`、windows-library `120834897238`、macos-core `120834897292`、macos-library `120834897167`、report `120835503732` |

守卫（每个作业首步）：`HEAD == GITHUB_SHA`、起点为祖先、SDK 保护树与实现起点相等、产品 schema 不变、
`git diff --name-only <start> HEAD` 全部落在本包白名单（`tests/reader_distribution_inventory/**`、
本工作流、`docs/READER-DISTRIBUTION-INVENTORY.md`、`docs/validation/reader-distribution-inventory.json`）。

## 2. 六份实际安装结果

`reading-core` 与 `reading-library` 各自干净配置、构建、安装（`cmake --preset` → `build` → `install`），
下述数字都取自安装后的 stage，不是 CMake 开关推断：

| 平台 | preset | 文件 | 安装字节 | 分发包内归档 | 符号边 | 动态依赖 | 具名检查 | 工件 ID | ZIP 字节 | ZIP SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Ubuntu 22.04 | reading-core | 262 | 18,541,669 | 21 | 41 | 3 | 24 | 12555386763 | 7,009,782 | `aabd023662b8…` |
| Ubuntu 22.04 | reading-library | 265 | 20,442,359 | 23 | 46 | 3 | 24 | 12555381712 | 7,846,207 | `eafccceec7cb…` |
| Windows 2022 | reading-core | 262 | 25,597,160 | 21 | 39 | 2 | 24 | 12555386869 | 10,839,409 | `d4829ef87fe9…` |
| Windows 2022 | reading-library | 265 | 29,084,761 | 23 | 43 | 2 | 24 | 12555167866 | 12,445,680 | `474c5d8984d5…` |
| macOS 15 | reading-core | 262 | 14,859,768 | 21 | 41 | 1 | 24 | 12555516241 | 6,343,750 | `81e2b01d94cb…` |
| macOS 15 | reading-library | 265 | 16,652,242 | 23 | 46 | 1 | 24 | 12554849898 | 7,189,370 | `3a68e544fbc3…` |

ZIP digest 只列前 12 位，完整值见 `docs/validation/reader-distribution-inventory.json` 的同名 `digest` 字段。

六份工件的 `expires_at` 均为 `2027-01-22T09:14:23Z`；`workflow_run.id/head_sha` 同源，
大小与 digest 与各自上传日志中的 "Final size / Artifact ID / SHA256 digest" 逐字核对通过。

**版本身份三处一致**：安装后的公共头 `include/exr/base.h`（`EXR_VERSION 3.40.0`、`EXR_ABI_VERSION 1`、
`EXR_CORE_VERSION 3.39.0`）、安装后的 `EXReaderConfigVersion.cmake`、以及用安装后公共 API 编出的探针
`exr_version()/exr_abi_version()` 运行时输出。六份安装全部是 3.40.0 / ABI 1 / core 3.39.0。

## 3. 依赖证据：命令、原始输出与清单逐字对应

每个安装记录 45–55 条真实命令，原始输出原文随工件上传（`tools/NN-*.txt`），清单只陈述这些输出能证明的事实：

| 证据 | 命令 | 用途 |
| --- | --- | --- |
| 归档成员 | `ar t`（Linux/macOS）、`lib /nologo /list`（Windows） | 每个分发归档里到底有哪些对象 |
| 符号集 | `nm`（Linux/macOS）、`dumpbin /nologo /symbols`（Windows） | 每个归档提供/需要的外部符号 |
| 静态链接图 | 未定义符号 ∩ 其他归档已定义符号 | 归档之间的真实依赖边（不读 CMake 链接意图） |
| 链接行 | `ninja -t commands probe` | 安装后探针程序的实际链接命令 |
| 动态依赖 | `readelf -d` + `ldd` / `otool -L` / `dumpbin /dependents` | 安装后消费者实际导入的系统库 |

- linux-core 记录 51 条：`ar` 27（21 个分层/私有归档 + 6 个上游名副本）、`nm` 21、`ninja-link` 1、`readelf-dynamic` 1、`ldd` 1。
- windows-core 记录 50 条：`lib-list` 27、`dumpbin-symbols` 21、`ninja-link` 1、`dumpbin-dependents` 1。
- 真实静态依赖示例（linux-core）：`libexr_vendor_tiff.a → libexr_vendor_zlibstatic.a`（`deflate`、`deflateEnd`、`deflateInit_`…）、
  `libexr_layout.a → libexr_vendor_freetype.a`（`FT_Get_Char_Index`、`FT_Face_GetCharVariantIndex`…）、
  `libexr_pdf.a → libexr_vendor_freetype.a`（`FT_Done_Face`、`FT_Get_CID_From_Glyph_Index`…）。
- 符号图覆盖全部 21/23 个分发归档，没有"装了但没有任何入边"的归档（`archives.reachability` 六份全 pass）。
- 探针链接 `EXReader::exreader` + `EXReader::exr_pdf`（library 另加 `EXReader::exr_library`），
  因此每个安装的**全部**归档都出现在实际链接命令里；任何"清单里有、链接行没有"的归档都会被拒。
- 实际动态依赖：Linux `libm.so.6`、`libc.so.6`、`ld-linux-x86-64.so.2`；macOS `/usr/lib/libSystem.B.dylib`；
  Windows `KERNEL32.dll`、`SHELL32.dll`（`/MT` 静态 CRT，所以没有 CRT 导入）。

聚合作业从工件字节重新做一遍：重算每个安装文件的字节与 SHA-256/SHA-1、重解析每条命令输出并与清单逐字比对、
用重解析出的符号集重算依赖边与集合散列、重算链接行的分发归档与系统库、重跑禁用项扫描、
重算 SPDX 的 `PackageVerificationCode`、并用官方 schema 校验两份 SBOM。

## 4. 许可证原文与 notice 来源

复用既有许可记录 `tools/check_reading_licenses.py`（`COMPONENTS` 22 项登记）作为唯一事实源；
本包不重写登记表，只做"安装字节 ↔ 登记固定散列 ↔ 上游原路径"的三方核对，并把结果写进 SBOM。

| 项目 | reading-core | reading-library |
| --- | --- | --- |
| 登记组件 | 22 | 22 |
| 本 preset 启用 | 19 | 20（+SQLite） |
| 登记材料条目 | 25 | 26 |
| `share/exreader/licenses/` 安装文件 | 21 | 22 |
| 既有检查器结论 | `release_ready=true`、`failures=[]`、`pending=[]`、`mandatory_missing=[]` | 同左 |

"登记材料条目"= `share/exreader/licenses/**` 下的第三方原文 + 仓库根 `LICENSE`、`share/exreader/LICENSE`、
`THIRD_PARTY_NOTICES.md` 与 `share/exreader/THIRD_PARTY_NOTICES.md` 两份。

| 组件 | 版本 | 许可证（登记值） | 安装原文 | 上游原路径 |
| --- | --- | --- | --- | --- |
| FreeType | VER-2-15-0 | FTL OR GPL-2.0-only；选 FTL | `freetype/FTL.TXT`、`freetype/LICENSE.TXT` | `docs/FTL.TXT`、`LICENSE.TXT` |
| Expat | R_2_9_0 | MIT | `expat/COPYING`、`expat/upstream-root/COPYING` | `expat/COPYING`、根 `COPYING` |
| miniz | 3.1.2 | MIT | `miniz/LICENSE` | `LICENSE` |
| stb_image | 2c980bb5… | MIT OR public domain；选 MIT | `stb/LICENSE` | `LICENSE` |
| libwebp | v1.5.0 | BSD-3-Clause | `libwebp/COPYING`、`libwebp/PATENTS` | `COPYING`、`PATENTS` |
| zlib | v1.3.1 | Zlib | `zlib/LICENSE` | `LICENSE` |
| libtiff | v4.7.0 | libtiff（BSD 风格） | `libtiff/LICENSE.md` | `LICENSE.md` |
| libaom | af3dc9aa（3.15.2） | BSD-2-Clause AND AOM Patent License 1.0 | `libaom/LICENSE`、`libaom/PATENTS` | `LICENSE`、`PATENTS` |
| libavif | v1.2.0 | BSD-2-Clause | `libavif/LICENSE` | `LICENSE` |
| Mbed TLS 子集 | mbedtls-3.6.7 | Apache-2.0 OR GPL-2.0-or-later；选 Apache-2.0 | `mbedtls/LICENSE` | `LICENSE` |
| OpenJPEG | 2.5.4 | BSD-2-Clause | `openjpeg/LICENSE` | `LICENSE` |
| LittleCMS | lcms2.19.1 | MIT | `lcms/LICENSE` | `LICENSE` |
| SQLite | 3.54.0 | Public domain（随包来源声明） | `sqlite/sqlite-public-domain.txt` | 仓库 `licenses/sqlite-public-domain.txt` |
| Unicode 派生表 | 17.0.0 与 3.2 | Unicode-3.0 | `unicode/LICENSE.txt` | 仓库 `tests/fixtures/unicode/LICENSE.txt` |
| Argyll CMYK 配置 | 仓库数据 | Public domain（原始 notice） | `default-cmyk-profile.txt` | 仓库 `licenses/default-cmyk-profile.txt` |
| Adobe Glyph List | 4036a9ca… | BSD-3-Clause | `pdf-font-data/adobe-glyph-list.txt` | 仓库 `licenses/adobe-glyph-list.txt` |
| PDF.js 编码/度量事实 | 81525fd4… | Apache-2.0 | `pdf-font-data/pdfjs.txt` | 仓库 `licenses/pdfjs.txt` |
| PostScript 计算器操作名 | PDF 32000-1 表 42 | Adobe 许可声明 | 仅 `THIRD_PARTY_NOTICES.md` 段落（无独立原文） | 同上 |
| Noto Sans 测试字体（仅声明） | 仓库 fixtures | OFL-1.1 | `wp7-fonts/noto-sans-test-fonts.txt` | 仓库 `licenses/noto-sans-test-fonts.txt` |

notice 来源两处交叉：安装原文的上游路径/固定散列，与 `THIRD_PARTY_NOTICES.md` 中该组件的段落标记
（`notices_sha256` 固定）。缺任一即 `licenses.notices_described` 或 `licenses.installed_matches_pin` 失败。

**有争议/需 root 收口的许可项**（只列依据与未解项，不做法律判断）：

| 项目 | 依据 | 未解项 |
| --- | --- | --- |
| FreeType 双许可 | 上游同时给 `FTL.TXT` 与 `LICENSE.TXT`；notice 声明选 FTL | 分发物按 FTL 还是 GPL-2.0-only 归责，需发布人决定 |
| libaom `PATENTS` | 上游 `PATENTS` 是附加专利授权，不是版权许可，SPDX 表达式写作 `AND LicenseRef-AOM-Patent-License-1.0` | 许可证表达式是否被商店/下游 SBOM 工具接受 |
| libtiff | 上游是 BSD 风格自有文本，无标准 SPDX id；SBOM 用 `LicenseRef-libtiff` | 是否需要映射到 `BSD-3-Clause` 近似值 |
| SQLite | 上游无 LICENSE 文件，只有 `sqlite3.c` 头部 dedication | 随包声明是否足以覆盖分发义务 |
| PDF.js 数据 | 固定 commit 的仓库根只有 `LICENSE`，`src/core/` 无 NOTICE；已按既有记录安装 `licenses/pdfjs.txt` | 该目录是否另有上游 NOTICE 需发布人确认 |
| PostScript 操作名 | 仅有 notice 段落，无独立原文可安装 | 是否需要在分发物中附带更完整的 Adobe 声明 |
| FAAD2 / minimp3 | 已登记但本配置**未启用**（GPL-2.0-or-later / CC0-1.0），六份安装中既无归档也无原文 | 音频构建另行验收；本清单不对其作任何结论 |

## 5. 机器可读 SBOM

同一次安装同时产出两份标准文档，内容只描述这一份实际 stage：

| 文档 | 结构 | 字节 | SHA-256（linux-core / linux-library） |
| --- | --- | ---: | --- |
| SPDX 2.3 JSON | 1 复用文档 + 1 SDK 包（`filesAnalyzed=true`、`PackageVerificationCode`）+ 18/19 第三方包 + 262/265 文件元素 + `DESCRIBES`/`CONTAINS`/`DEPENDS_ON` 关系（共 19/20 包） | 217,247 / 220,603 | `7f92dfc77104…` / `17e8fc921000…` |
| CycloneDX 1.5 JSON | `metadata.component` = SDK；组件 = 18/19 库 + 262/265 文件（共 280/284 组件）；`dependencies` 由符号边导出 | 130,084 / 132,436 | `5096dae9e417…` / `c514ab20ba79…` |

- SPDX `PackageVerificationCode` 按 7.9.4 算法由安装文件 SHA-1 重算，聚合侧独立复算比对。
- 许可证标识来自显式表（`sbom.LICENSES`），未登记的组件 id 会让生成直接失败，不允许"猜一个 id"。
- schema 校验用官方文档：SPDX `v2.3` `schemas/spdx-schema.json`；CycloneDX `master` `schema/bom-1.5.schema.json`
  及其 `spdx.schema.json`、`jsf-0.82.schema.json`，在 report 作业内用 `jsonschema` 校验，取不到 schema 即失败。
- 两份文档内的路径全部是 stage 相对路径；生成后对自身字节再扫一遍，确认没有构建机绝对路径。

## 6. reading 配置范围：不该混入的项实测

| 检查项 | 结果 |
| --- | --- |
| 21 个 `EXR_*` 缓存开关 vs preset 解析值 | 六份全部一致 |
| 模块层 | 8 层（base/graphics/text/doc/formats/layout/render/pdf）；library preset 另加 library |
| 音频/GPL | `EXR_ENABLE_AUDIO/MP3/AAC` 全 OFF；无 audio 层；无 minimp3/FAAD2 归档与原文 |
| 未启用可选模块 | `EXR_ENABLE_PDF_EDIT`、`EXR_ENABLE_TEXT_INDEX`、`EXR_BUILD_TEXT_INDEX`、`EXR_BUILD_SHARED_COMPAT`、`EXR_BUILD_JNI`、`EXR_BUILD_TOOLS`、`EXR_BUILD_TESTS`、`EXR_BUILD_FUZZ` 全 OFF；stage 内无对应目标产物 |
| WebView / WebKit / Chromium / Electron / CEF | 文件名、导出 CMake 目标、动态依赖三处都没有 |
| 测试凭据 | 安装包未导出 `EXReaderCredentials`，stage 内无 `*credential*` 材料 |
| 已生成材料里的构建机路径 | 两份 SBOM 与 `inventory.json` 自身扫描为 0 处 |
| 已安装文件里的构建机路径 | **仍存在**，见第 7 节 |
| 上游名重复归档 | 每份安装 6 个（`lib/libaom`、`lib/libsharpyuv`、`lib/libwebp`、`lib/libwebpdecoder`、`lib/libwebpdemux`、`lib/libwebpmux`），与 `lib/exreader/libexr_vendor_*` 内容重复；linux-core 合计 3,854,370 B，占该 stage 20.8%。记为 `archives.foreign_copies=reported`，由 root 决定是否从分发物里去掉 |

## 7. 发布阻断项（共享缺陷，交 root 收口）

三类、六份安装共 96 处。全部由"安装字节里出现构建机绝对路径"这一条实测规则发现，
聚合作业用通用前缀（`/home/runner/`、`/Users/runner/`、`D:\a\`、`C:\Users\`、`C:/Users/`）从工件字节独立复核过。

| 类别 | 文件（六份合计） | 命中内容 | 来源 | 建议修法（本包不改，改动落在白名单外） |
| --- | --- | --- | --- | --- |
| 文档 | `docs/CONVERSION.md`（第 189 行）、`docs/WP7-SCRIPTS.md`（第 110–118 行） | `C:/Users/Oscar/…` | 仓库文档正文；由 `CMakeLists.txt:1017` 安装进 `docs/` | 把示例路径改成相对路径（`build/wp12-lite-corpus`、`build/wp7`） |
| 上游 pkg-config | `lib/pkgconfig/{aom,libsharpyuv,libwebp,libwebpdecoder,libwebpdemux,libwebpmux}.pc`（Linux/macOS 各 6） | `prefix=/home/runner/…/stage` 或 `/Users/runner/…` | libwebp / libaom 自己的 `install()` 规则 | 不随 SDK 安装这些 `.pc`，或改写为 `prefix=${pcfiledir}/../..` |
| 归档内嵌路径 | Linux/macOS：`lib/exreader/libexr_vendor_tiff.a`；Windows：全部 `.lib`（core 21 个 / library 23 个） | `/home/runner/…/libtiff/tif_dir.c`（libtiff 的 `__FILE__` 错误串）、`D:\a\…`（MSVC 归档成员记录） | 依赖源码编译时的绝对路径 | 依赖开启 `-ffile-prefix-map`/`/pathmap`；MSVC 归档改用相对对象路径生成 |

最小复现（云端，无需本包脚本）：

```bash
cmake --preset reading-core && cmake --build --preset reading-core && cmake --install build/reading-core
grep -rl 'C:/Users/' build/reading-core/stage/docs            # CONVERSION.md, WP7-SCRIPTS.md
grep -ral '/home/runner/' build/reading-core/stage/lib        # pkgconfig/*.pc, exreader/libexr_vendor_tiff.a
```

在本包判定里这些是 `release_blockers` 而不是 `problems`：它们不影响"清单/散列/依赖/许可材料是否被证明"，
只影响"这份安装能不能对外分发"。所以第 2 节的作业可以全绿、`materials_complete=true`，
而 `release_ready=false` 并逐条列出文件。**不得**把 `materials_complete=true` 读成发布就绪。

## 8. 未覆盖范围

- Android、iOS、Apple 原生宿主打包（各自 owner）；
- GTK/Linux、Windows、macOS 原生宿主包与 Noto Sans CJK 宿主字体；
- 音频构建（`EXR_ENABLE_AUDIO` 与 MP3/AAC）——本配置按设计排除，本清单不对它作任何结论；
- PDF 编辑、文本索引、共享兼容库、JNI 绑定、工具与测试二进制；
- 离线安装器、代码签名、公证、tag/Release、商店发布；
- 法律结论：登记的是许可证标识与原文，不是合规判定。

## 9. 复现方式

```bash
# 守卫 + 反例回归（无需编译器）
bash tests/reader_distribution_inventory/check_scope.sh
python3 tests/reader_distribution_inventory/check_inventory.py

# 单份安装：既有许可记录 + 本包清单/SBOM
python3 tools/check_reading_licenses.py reading-core build/reading-core build/reading-core/stage build/reading-core/licenses.json --require-release-ready
python3 tests/reader_distribution_inventory/inventory.py --profile reading-core --platform linux --runner-os Linux \
  --build build/reading-core --stage build/reading-core/stage --licenses build/reading-core/licenses.json \
  --consumer build/reading-consumer/reading-document --probe build/probe/probe --probe-build build/probe \
  --output build/reading-core/inventory

# 同源聚合（可对已完成 run 重跑）
python3 tests/reader_distribution_inventory/aggregate.py --downloads build/downloads --output build/aggregate \
  --spdx-schema spdx-schema.json --cdx-schema bom-1.5.schema.json --run-id 40081161966 --attempt 1 --source-sha f3b5c8f6…
```

反例回归当前覆盖：4 个正控（linux/windows/macos 夹具 + 已声明阻断项不污名化证据）、37 个拒绝
（漏文件、多文件、散列错、空文件、缺 notice、原文被改、未登记原文、SBOM 缺文件/散列错/身份错、
依赖输出被改、编造静态边、归档散列错、链接行/系统库/动态依赖不符、音频开关被打开、未声明路径、
许可记录未就绪、版本三处不一致、非法工件路径、run/source 不符、检查状态非法、上游名归档声明不符…），
4 项工具输出解析自检、6 项工件身份/ZIP 拒绝（ZIP digest、过期、他人 run、上传大小/摘要不符、重复路径）。

## 10. 本轮迭代与保留的失败

| run | 结果 | 原因（本包实现缺陷，均已修复；旧记录不用于本轮验收） |
| --- | --- | --- |
| 40076871953 | failure | 首方 `LICENSE`/`THIRD_PARTY_NOTICES.md` 被当作 licenses 目录材料比对 |
| 40077076410 | failure | 同一处存在性检查仍然只看 licenses 目录 |
| 40077307329 | failure | 5 例夹具改安装却没留文件记录；SBOM 结构失败未带原因 |
| 40077611836 | failure | `dumpbin` 依赖块被它自己的空行截断 |
| 40077966666 | failure | COFF 段符号被当成可链接符号 |
| 40078277226 | failure | 探针没有前置安装前缀；Windows 编译器环境用了未加花括号的 `env:` 形式 |
| 40078844006 | failure | 本包自身检查的三处缺陷：版本身份传参、notice 作用域、符号定义优先 |
| 40079459218 | failure | 布局列表在 `pipefail` 下提前关闭管道；其余 5 份安装已绿 |
| 40079877588 | success | 六份全绿、`accepted=true`；随后补充"上游名副本"记录而被本轮取代 |
| 40080548788 | failure | 归档扫描解包四个列表却只初始化三个 |

本轮（40081161966）之前的每一次失败都原样保留在 Actions 里，未被改写成"预期拒绝"。

## 11. 交回清单

- 受测源码 `f3b5c8f65d6a1d7db51364b897f81a995ce37c67`，分支 `codex/reader-distribution-inventory`；
  本文与 `docs/validation/reader-distribution-inventory.json` 为其后继纯证据提交（`[skip ci]`）。
- 六份工件 ID/字节/digest/有效期见第 2 节；逐平台 job id 见第 1 节；report 作业 `120835503732` 产出
  `aggregate.json`（`accepted=true`、`inventory_generated=true`、`materials_complete=true`、`release_ready=false`）。
- 需 root 处理：第 7 节三类路径泄漏（含最小复现与建议补丁）、第 4 节许可争议项、第 6 节上游名重复归档是否保留。
- 未授予：发布就绪、移动/宿主打包、签名与正式发布。
