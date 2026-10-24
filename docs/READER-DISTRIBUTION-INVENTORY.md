# G09：产品依赖、许可证与离线分发清单

固定实现起点 `f43baf9182d75907c0cb5d6f77048f27bca8c950`，分支 `codex/reader-distribution-inventory`。
本文件是离线分发材料：**两个 profile** 的实际安装内容。

| profile | 内容 | 用途 |
| --- | --- | --- |
| `reading-core` / `reading-library` | 只有阅读 SDK（无音频、无 WebView、无凭据模块、无任何可选应用包） | 阅读发布的默认配置 |
| `combined` | `reading-library` + 固定起点已有的 **13 个可选应用包**，装进同一个 prefix 并显式登记 | 组合分发的依赖与许可材料 |

**两个出口分开记录：**

| 出口 | 结果 | 依据 |
| --- | --- | --- |
| 生成材料（清单 + 依赖 + 许可材料 + SBOM），六个 SDK 安装 + 三个组合 prefix | 通过 | run [40095313750](https://github.com/NoGod3524/EXReader/actions/runs/40095313750) attempt 1，**11/11 作业成功**，九份安装工件同源、非空、未过期、digest 与上传日志一致 |
| 发布就绪 | **未授予** | 九份安装中共 60 处不同文件仍携带构建机绝对路径（第 8 节）。修复落在共享文档、上游安装规则与受保护构建配置，不由本包改动 |

授予范围：九份桌面安装的逐文件清单/散列、真实静态与动态依赖、登记许可证原文与 notice 来源、
两份标准 SBOM，以及"未启用项确实没有混入 / 已启用项确实被登记"的实测。
不含 Android/iOS/Apple 宿主打包、宿主字体、签名/公证、tag/Release/商店发布，也不含法律结论。

## 1. 受测身份与云端出口

| 项目 | 值 |
| --- | --- |
| 受测源码 | `93d2ad0db2d75af50eddc0843a4da9c7090a15aa` |
| 实现起点（祖先约束） | `f43baf9182d75907c0cb5d6f77048f27bca8c950` |
| 冻结 SDK 保护树 | `9854061be331fe603a1822d9b2b36ee357154927`（与受测源码逐字节相同） |
| 产品 schema | `apps/reader/store/001_catalog.sql` 与实现起点相同 |
| 工作流 | `.github/workflows/reader-distribution-inventory.yml` |
| run / attempt | [40095313750](https://github.com/NoGod3524/EXReader/actions/runs/40095313750) / 1，success |
| 作业（11） | protocol `120876184613`；SDK：linux-core `120876212765`、linux-library `120876212746`、win-core `120876212743`、win-library `120876212790`、macos-core `120876212787`、macos-library `120876212827`；组合：linux `120876212706`、win `120876212732`、macos `120876212742`；report `120877173430` |

守卫（每个作业首步）：`HEAD == GITHUB_SHA`、起点为祖先、SDK 保护树与实现起点相等、产品 schema 不变、
`git diff --name-only <start> HEAD` 全部落在本包白名单。

## 2. 六份阅读 SDK 实际安装结果

`reading-core` / `reading-library` 各自干净配置、构建、安装；数字取自安装后的 stage，不是 CMake 开关推断：

| 平台 | preset | 文件 | 安装字节 | 归档 | 符号边 | 动态依赖 | 具名检查 | 工件 ID | ZIP 字节 | ZIP SHA-256 | 路径命中 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Ubuntu 22.04 | core | 262 | 18,541,669 | 21 | 41 | 3 | 24 | 12560228214 | 7,009,765 | `7b3621e5b370…` | 9 |
| Ubuntu 22.04 | library | 265 | 20,442,359 | 23 | 46 | 3 | 24 | 12560990895 | 7,846,205 | `c26231709ad4…` | 9 |
| Windows 2022 | core | 262 | 25,597,160 | 21 | 39 | 2 | 24 | 12560284508 | 10,839,347 | `af8535193c75…` | 29 |
| Windows 2022 | library | 265 | 29,084,761 | 23 | 43 | 2 | 24 | 12560063652 | 12,445,794 | `2e661981d084…` | 31 |
| macOS 15 | core | 262 | 14,859,768 | 21 | 41 | 1 | 24 | 12560692120 | 6,343,653 | `8fd2fd62358f…` | 9 |
| macOS 15 | library | 265 | 16,652,242 | 23 | 46 | 1 | 24 | 12561006365 | 7,189,316 | `0886e909ff48…` | 9 |

九份工件的 `expires_at` 均为 `2027-01-22T12:46:21Z`；`workflow_run.id/head_sha` 同源，
大小与 digest 与各自上传日志的 "Final size / Artifact ID / SHA256 digest" 逐字核对通过。

**版本身份三处一致**：安装后的公共头（`EXR_VERSION 3.40.0`、`EXR_ABI_VERSION 1`、`EXR_CORE_VERSION 3.39.0`）、
安装后的 `EXReaderConfigVersion.cmake`、以及用安装后公共 API 编出的探针运行时输出。

## 3. 三份组合 prefix：SDK + 13 个可选应用包

组合作业把 `reading-library` 与固定起点已有的 13 个可选包装进同一个 prefix，逐个包按**安装后的字节**取证：

| 平台 | 文件 | 安装字节 | 归档 | 符号边 | 具名检查 | 工件 ID | ZIP 字节 | ZIP SHA-256 | 路径命中 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Ubuntu 22.04 | 350 | 24,093,888 | 44 | 87 | 90 | 12560936421 | 9,197,595 | `9ad81d61fc8c…` | 9 |
| Windows 2022 | 350 | 39,660,921 | 44 | 70 | 90 | 12561245295 | 16,593,113 | `958d2bf9df49…` | 46 |
| macOS 15 | 350 | 19,940,742 | 44 | 87 | 90 | 12560612560 | 8,489,862 | `63ca00e9ec3b…` | 9 |

每个包在 `combined.json` 里都有：`version`（来自它自己的 `*ConfigVersion.cmake`）、
公开头清单与 SHA-256、归档清单与 SHA-256、package config 目录内每个文件的 SHA-256、
许可原文的安装路径与 SHA-256、`external_*`（前缀内无法解释的未定义符号与所属系统库）、
以及该包 consumer 的**实际链接命令**与从中解析出的前缀归档/系统库/框架。

| 包（package 名） | 版本 | 归档 | 头 | 许可原文来源 | 真实外部依赖（Linux / Windows / macOS） |
| --- | --- | ---: | ---: | --- | --- |
| catalog `EXReaderProductCatalog` | 0.1.0 | 2 | 2 | 共享 `share/exreader/LICENSE` | SQLite **随包**（`reader_catalog_sqlite` + `share/exreader-product/sqlite-public-domain.txt`）；无外部数据库 |
| revisions `EXReaderRevisions` | 0.3.0 | 2 | 2 | 共享 | 无 |
| commands `EXReaderCommands` | 0.1.0 | 1 | 1 | 共享 | 无（经 revisions） |
| desktop-metadata `EXReaderDesktopMetadata` | 0.1.0 | 1 | 1 | 共享 | 无 |
| webdav `EXReaderWebDAV` | 0.2.0 | 1 | 1 | **自有** `share/exreader-webdav/LICENSE.txt` | TLS/XML：`libcurl`+`libxml2` / `winhttp`+`xmllite`+`shlwapi` / `libcurl`+`libxml2`（SDK 内 `.tbd`） |
| session `EXReaderSession` | 0.1.0 | 1 | 1 | 共享 | 继承 sync+webdav：`libcrypto,libcurl,libxml2` / `bcrypt,winhttp,xmllite,shlwapi` / `libcurl,libxml2` |
| sync `EXReaderSync` | 0.1.0 | 1 | 1 | 共享 | 摘要：`libcrypto`（OpenSSL）/ `bcrypt` / 无（CommonCrypto 在 libSystem 内） |
| credentials `EXReaderCredentials` | 0.1.0 | 1 | 1 | **自有** `share/exreader-credentials/LICENSE.txt` | keyring：`libsecret-1`（+gio/glib/gobject）/ `advapi32` / `Security`+`CoreFoundation` 框架 |
| reading-state `EXReaderReadingState` | 0.1.0 | 1 | 1 | 共享 | 无 |
| search `EXReaderSearch` | 0.1.0 | 1 | 1 | 共享 | 无 |
| preferences `EXReaderPreferences` | 0.1.0 | 1 | 1 | 共享 | 无 |
| batch-import `EXReaderBatchImport` | 0.1.0 | 1 | 1 | 共享 | 无 |
| sideload `EXReaderSideload` | **无版本文件** | 1 | 1 | 共享 | `bcrypt`（仅 Windows） |

- `sideload` 的 CMakeLists 只写 `EXReaderSideloadConfig.cmake`，不产生 `ConfigVersion.cmake`，
  因此 `find_package(EXReaderSideload)` 不能带版本约束。本清单把它登记为**无版本包**并记为
  `reported`，不假装它有版本；是否补版本文件由该包 owner 决定。
- `webdav` 的 `include/exr_webdav_android.h` 只在 Android 下安装，桌面登记里不要求它。
- Windows 的链接命令总是带默认系统库集合（`kernel32/user32/gdi32/shlwapi…`），
  所以那里的**决定性证据是符号通道**（`__imp_WinHttpOpen` → winhttp、`__imp_CredWriteW` → advapi32）。

## 4. 依赖证据：命令、原始输出与清单逐字对应

| 证据 | 命令 | 用途 |
| --- | --- | --- |
| 归档成员 | `ar t`（Unix）、`lib /nologo /list`（Windows） | 每个分发归档里有哪些对象 |
| 符号集 | `nm -g`、`dumpbin /nologo /symbols` | 归档提供/需要的外部符号 |
| 默认库指令 | `dumpbin /nologo /directives` | Windows 归档自己要求的默认库 |
| 静态链接图 | 未定义符号 ∩ 其他归档已定义符号 | 归档之间的真实依赖边 |
| 链接命令 | `ninja -t commands <consumer>` | 每个可选包 consumer 的真实链接行 |
| 动态依赖 | `readelf -d`+`ldd` / `otool -L` / `dumpbin /dependents` | 安装后消费者实际导入的系统库 |

- 六个 SDK 安装各记录 45–50 条命令；三份组合 prefix 各记录 `44 个归档 × 2–3` 加 `13 条链接命令`。
- 组合 prefix 的真实静态边：linux/macOS 87 条、Windows 70 条，覆盖 44 个归档（9 个 SDK 分层 + 14 个 SDK 私有 + 15 个包归档 + 6 个上游名副本）。
- 依赖分类：每个链接 token 先落成真实文件名，再判定它属于**前缀内归档**还是**系统库**；系统库再按登记族与符号家族交叉核对。
  登记期望缺失即失败（例如 webdav 少了 `libcurl`、credentials 少了 `libsecret-1`）。
- 聚合作业从工件字节重做一遍：重算每个安装文件的字节与 SHA-256/SHA-1、重解析每条命令输出并逐字比对、
  用重解析出的符号集重算依赖边与集合散列、重算链接行的前缀归档与系统库、重跑禁用项与密钥扫描、
  重算 SPDX 的 `PackageVerificationCode`，并用官方 schema 校验九份 SBOM。

## 5. 许可证原文与 notice 来源

复用既有许可记录 `tools/check_reading_licenses.py`（22 项登记）作为 SDK 部分的唯一事实源；13 个应用包按
"自有原文 / 共享原文" 两种解析登记，两种都要求安装后确实存在且散列一致。

| 项目 | reading-core | reading-library | combined |
| --- | --- | --- | --- |
| 登记组件 | 22 | 22 | 22 + 13 包 |
| 本 profile 启用 | 19 | 20 | 20 + 13 |
| 登记材料条目 | 25 | 26 | 26 + 13 |
| 原文文件数 | 21 | 22 | 22 + 2（自有）+ 11 引用共享 |
| 既有检查器结论 | `release_ready=true` | 同左 | 同左 |

- 13 个包都是仓库首方代码，MIT；`webdav` 与 `credentials` 各自安装一份原文，
  其余 11 个包以同一 prefix 内的 `share/exreader/LICENSE` 为准（登记为 `shared`，并在清单里写明来源）。
- 第三方许可证原文、notice 段落与争议项（FreeType 双许可、libaom PATENTS、libtiff 自有文本、SQLite 声明、
  PDF.js 数据、PostScript 操作名、未启用的 FAAD2/minimp3）与上一轮一致，依据与未解项见
  `docs/validation/reader-distribution-inventory.json` 的 `licence_record` 与 `release_blockers` 邻接段落。

## 6. 机器可读 SBOM

同一次安装同时产出两份标准文档，内容只描述这一份实际安装：

| 文档 | 结构 | 字节（SDK core/library；组合 linux） |
| --- | --- | ---: |
| SPDX 2.3 JSON | 复用文档 + SDK 包（`filesAnalyzed=true`、`PackageVerificationCode`）+ 第三方/应用包 + 文件元素 + `DESCRIBES`/`CONTAINS`/`DEPENDS_ON` 关系 | 217,247 / 220,603 / 296,980 |
| CycloneDX 1.5 JSON | `metadata.component` = SDK；组件 = 库 + 文件；`dependencies` 由符号边导出 | 130,084 / 132,436 / 180,750 |

（三列依次为 reading-core、reading-library、combined(linux)；Windows/macOS 的字节数接近，完整散列见工件与验证 JSON。）

- SPDX `PackageVerificationCode` 按 7.9.4 算法由安装文件 SHA-1 重算，聚合侧独立复算比对。
- 许可证标识来自显式表（`sbom.LICENSES`）：SDK 第三方按登记，13 个应用包按首方 MIT；未登记的组件 id 会让生成直接失败。
- schema 校验用官方文档：SPDX `v2.3` 与 CycloneDX `master` `schema/bom-1.5.schema.json`（含 `spdx.schema.json`、`jsf-0.82.schema.json`），
  在 report 作业内用 `jsonschema` 校验，取不到 schema 即失败。
- 两份文档只含 stage 相对路径；生成后对自身字节再扫一遍构建机路径。

## 7. 两个 profile 的边界实测

| 检查项 | reading-* | combined |
| --- | --- | --- |
| 21 个 `EXR_*` 缓存开关 vs preset | 六份一致 | 一致（reading-library preset） |
| 音频/GPL | `EXR_ENABLE_AUDIO/MP3/AAC` 全 OFF，无 audio 层/归档/原文 | 同左 |
| WebView/WebKit/Chromium/Electron/CEF | 文件、导出目标、动态依赖三处都没有 | 同左 |
| 凭据模块 | 安装包不导出 `EXReaderCredentials`，stage 内无 `*credential*` 材料 | **显式登记**：prefix 内的凭据材料必须全部来自该包（`packages.credentials_registered`） |
| 可选应用包 | 一个都不出现（`packages.registered` 只在 combined 里核对） | 13 个全部出现且与登记一致 |
| 测试密钥 | 无 PEM 私钥/访问密钥形状 | 同左（`inclusions.no_test_secrets`） |
| 生成的 SBOM 内构建机路径 | 0 处 | 0 处 |
| 已安装文件的构建机路径 | 见第 8 节 | 见第 8 节 |
| 上游名重复归档 | 每份 6 个（`libaom/libwebp*/libsharpyuv`），linux-core 占 20.8% 字节 | 同样 6 个，另加 13 个包的自有归档 |

## 8. 发布阻断项（共享缺陷，交 root 收口）

九份安装合计 **60 处不同文件**携带构建机绝对路径，聚合作业用通用前缀
（`/home/runner/`、`/Users/runner/`、`D:\a\`、`C:\Users\`、`C:/Users/`）从工件字节独立复核。

| 类别 | 文件 | 命中内容 | 来源 | 建议修法（本包不改） |
| --- | --- | --- | --- | --- |
| 文档 | `docs/CONVERSION.md`（189 行）、`docs/WP7-SCRIPTS.md`（110–118 行） | `C:/Users/Oscar/…` | 仓库文档正文，由 `CMakeLists.txt:1017` 安装 | 改成相对路径（`build/wp12-lite-corpus`、`build/wp7`） |
| 上游 pkg-config | `lib/pkgconfig/{aom,libsharpyuv,libwebp,libwebpdecoder,libwebpdemux,libwebpmux}.pc` | `prefix=/…/stage` | libwebp / libaom 自己的 `install()` | 不随 SDK 安装，或改写为 `prefix=${pcfiledir}/../..` |
| 归档内嵌路径 | Linux/macOS：`lib/exreader/libexr_vendor_tiff.a`；Windows：**全部** `.lib`（SDK 分层 + 私有依赖 + 13 个包归档 + 上游名副本，共 46 个） | `/home/runner/…/tif_dir.c`、`D:\a\…` | 依赖源码编译期绝对路径、MSVC 归档成员记录 | 依赖开启 `-ffile-prefix-map`/`/pathmap`；MSVC 归档改用相对对象路径生成 |

最小复现（云端）：

```bash
cmake --preset reading-core && cmake --build --preset reading-core && cmake --install build/reading-core
grep -rl 'C:/Users/' build/reading-core/stage/docs            # CONVERSION.md, WP7-SCRIPTS.md
grep -ral '/home/runner/' build/reading-core/stage/lib        # pkgconfig/*.pc, exreader/libexr_vendor_tiff.a
```

这些是 `release_blockers` 而不是 `problems`：它们不影响"清单/散列/依赖/许可材料是否被证明"，
只影响"这份安装能不能对外分发"。所以作业可以全绿、`materials_complete=true`，
而 `release_ready=false` 并逐条列出文件。**不得**把 `materials_complete=true` 读成发布就绪。

## 9. 未覆盖范围

- Android、iOS、Apple 原生宿主打包（各自 owner）；
- GTK/Linux、Windows、macOS 原生宿主包与 Noto Sans CJK 宿主字体；
- 音频构建（`EXR_ENABLE_AUDIO` 与 MP3/AAC）；PDF 编辑、文本索引、共享兼容库、JNI、工具与测试二进制；
- 可选包的**行为**（同步、订阅、导入、界面）：本清单只证明它们的安装材料、公开头和依赖接口；
- 离线安装器、代码签名、公证、tag/Release、商店发布；
- 法律结论。

## 10. 复现方式

```bash
bash tests/reader_distribution_inventory/check_scope.sh
python3 tests/reader_distribution_inventory/check_inventory.py      # 4 正控 + 37 拒绝 + 4 解析自检 + 6 工件拒绝
python3 tests/reader_distribution_inventory/check_combined.py       # 3 正控 + 25 拒绝

# 单个 SDK 安装
python3 tools/check_reading_licenses.py reading-core build/reading-core build/reading-core/stage build/reading-core/licenses.json --require-release-ready
python3 tests/reader_distribution_inventory/inventory.py --profile reading-core --platform linux --runner-os Linux \
  --build build/reading-core --stage build/reading-core/stage --licenses build/reading-core/licenses.json \
  --consumer build/reading-consumer/reading-document --probe build/probe/probe --probe-build build/probe \
  --output build/reading-core/inventory

# 组合 prefix（SDK + 13 包）
cmake --preset reading-library -DCMAKE_INSTALL_PREFIX="$PWD/build/prefix"
cmake --build --preset reading-library && cmake --install build/reading-library
python3 tools/check_reading_licenses.py reading-library build/reading-library build/prefix build/combined/licenses.json --require-release-ready
# …按工作流逐包 cmake -S <包源> -B <目录> -DCMAKE_PREFIX_PATH=build/prefix -DCMAKE_INSTALL_PREFIX=build/prefix…
cmake -S tests/reader_distribution_inventory/consumer_combined -B build/combined-consumers -DEXR_MODULE_PREFIX="$PWD/build/prefix"
cmake --build build/combined-consumers
python3 tests/reader_distribution_inventory/combined.py --prefix build/prefix --platform linux --runner-os Linux \
  --sdk-build build/reading-library --sdk-licenses build/combined/licenses.json \
  --consumers build/combined-consumers --output build/combined/inventory

# 同源聚合（也可对已完成 run 重跑）
python3 tests/reader_distribution_inventory/aggregate.py --downloads build/downloads --output build/aggregate \
  --spdx-schema spdx-schema.json --cdx-schema bom-1.5.schema.json --run-id 40095313750 --attempt 1 --source-sha 93d2ad0d…
```

拒绝回归当前覆盖：SDK 侧 4 正控 + 37 拒绝（漏文件、多文件、散列错、缺 notice、原文被改、SBOM 缺文件/散列错、
依赖输出被改、编造静态边、音频开关被打开、未声明路径、版本三处不一致、run/source 不符…）+ 6 项工件/ZIP 拒绝；
组合侧 3 正控 + 25 拒绝（漏某包的归档/头/许可原文、错版本、错 config、系统依赖未观测、链接行缺依赖、
混入测试密钥、前缀里出现未登记归档、编造依赖边、SBOM 覆盖/身份、凭据材料越界…）。

## 11. 本轮迭代与保留的失败

| run | 结果 | 原因（本包实现缺陷，均已修复；旧记录不用于本轮验收） |
| --- | --- | --- |
| 40076871953 | failure | 首方 `LICENSE` 被当作 licenses 目录材料比对 |
| 40077076410 | failure | 同一处存在性检查仍然只看 licenses 目录 |
| 40077307329 | failure | 5 例夹具改安装却没留文件记录；SBOM 结构失败未带原因 |
| 40077611836 | failure | `dumpbin` 依赖块被它自己的空行截断 |
| 40077966666 | failure | COFF 段符号被当成可链接符号 |
| 40078277226 | failure | 探针没有前置安装前缀；Windows 环境用了未加花括号的 `env:` |
| 40078844006 | failure | 本包自身检查的三处缺陷：版本身份传参、notice 作用域、符号定义优先 |
| 40079459218 | failure | 布局列表在 `pipefail` 下提前关闭管道；其余 5 份已绿 |
| 40079877588 | success | 六份 SDK 全绿；随后补充"上游名副本"记录而被取代 |
| 40080548788 | failure | 归档扫描解包四个列表却只初始化三个 |
| 40081161966 | success | 六份 SDK 全绿（上一轮交付）；13 个可选包仍在范围外 |
| 40090093085 | failure | SBOM 许可表没有 13 个包的标识 |
| 40090316414 | failure | 组合校验器里循环变量遮蔽了许可模块 |
| 40090749442 | failure | 组合夹具的许可条目缺上游路径 |
| 40090953542 | failure | 组合夹具的 directives 与归档符号缺省不完整 |
| 40091214370 | failure | link record 的存法与校验器读法不一致 |
| 40091417689 | failure | 夹具从部分上下文推导禁用项观测 |
| 40091586990 | failure | 校验器直接索引了工件里已不存在的声明文件 |
| 40091754101 | failure | 凭据材料路径大小写敏感比较 |
| 40091876911 | failure | 装在 licenses 目录外的固定散列许可被判缺失 |
| 40092058469 | failure | 安装归档名带 `lib` 前缀；sideload 无版本文件；WebDAV Android 头只在 Android 装 |
| 40092505702 | failure | Windows 的系统库由链接行而非 directives 给出；密钥标记命中代码常量 |
| 40093092263 | failure | macOS 上 ld64 拒绝 `-needed_library <target>`；同轮 ubuntu/windows 组合已绿 |
| 40093997798 | cancelled | 被 ld64 修复取代，未启动任何作业 |
| 40094346998 | failure | 过滤链接 flag 时把绝对路径库也一起丢掉 |
| 40094880635 | failure | 汇总读到自己作业的 `queued` 状态；九份安装全绿 |

本轮（40095313750）之前的每一次失败都原样保留在 Actions 里，未被改写成"预期拒绝"。

## 12. 交回清单

- 受测源码 `93d2ad0db2d75af50eddc0843a4da9c7090a15aa`，分支 `codex/reader-distribution-inventory`；
  本文与 `docs/validation/reader-distribution-inventory.json` 为其后继纯证据提交（`[skip ci]`）。
- 九份安装工件 ID/字节/digest/有效期与逐平台作业 ID 见第 1–3 节；report 作业 `120877173430` 产出
  `aggregate.json`（`accepted=true`、`inventory_generated=true`、`materials_complete=true`、`release_ready=false`、60 项阻断）。
- 需 root 处理：第 8 节三类路径泄漏（含最小复现与建议修法）、第 5 节许可争议项、第 3 节 `sideload` 无版本文件、
  第 7 节上游名重复归档是否保留。
- 未授予：发布就绪、移动/宿主打包、签名与正式发布、可选包的行为验收。
