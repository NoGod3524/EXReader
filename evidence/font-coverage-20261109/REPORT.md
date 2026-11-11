# 逐字形真实覆盖验收

640 个互不重复的 Unicode 码点，固定 `family=serif, style=regular`，每个都调用公开 pick API。
修复前：404 命中 / 209 管理器漏找 / 27 本机缺失。修复后：**613 命中 / 0 管理器漏找 / 27 本机缺失**。

[完整逐码点矩阵](matrix.md) · [修复前 236 项缺口](gaps-before.txt) · [最终 27 项缺口](gaps-after.txt)

| 集合 | 样本 | 命中 | 本机缺失 | 管理器漏找 |
|---|---:|---:|---:|---:|
| GB2312 一级 | 200 | 200 | 0 | 0 |
| CJK 扩展 A/B | 100 | 100 | 0 | 0 |
| 兼容区/异体字 | 50 | 23 | 27 | 0 |
| 假名/半角 | 60 | 60 | 0 | 0 |
| 韩文音节 | 50 | 50 | 0 | 0 |
| Emoji/ZWJ 组成码点 | 60 | 60 | 0 | 0 |
| 数学/符号 | 50 | 50 | 0 | 0 |
| 阿拉伯/希伯来 | 40 | 40 | 0 | 0 |
| 全角/半角 | 30 | 30 | 0 | 0 |

独立 FreeType 扫描了系统/用户字体目录及注册表所指的 349 个字体文件，372 个 collection faces；
manager 索引为 362 个可用 Unicode faces。每次命中都重开实际文件/face，检查 FT_Get_Char_Index 和 FT_Load_Glyph，
并确认该 face 真正出现在 create_font 的加载映射中。613 次命中的零索引/加载失败均为 0。
另测 31 个藏文字母：31/31 命中，管理器漏找 31 → 0。

## 修复

- 原五级优先顺序保留；移除不增加码点覆盖的冗余 face，再从已发现字体补充覆盖，标记 step 6。
- 自动补充部分优先彩色 face，避免单色符号字体抢先命中 emoji；v2 索引缓存保存颜色能力。
- 管理器的总字体字节上限增至 256 MiB，原始 exr_font_create 仍保持 128 MiB。此机最终加载 32 faces / 186,220,676 字节。
- 书内嵌入字体按需挤出自动补充链末端，保留配置字体优先级；加入满链嵌入字体回归。
- 新增同族同样式补充字形、冷/热缓存颜色优先、实际加载映射验证。

## 最终本机字体缺口（全部为 font_absent）

- U+FA83 — CJK COMPATIBILITY IDEOGRAPH-FA83：本机字体确实没有。
- U+FA99 — CJK COMPATIBILITY IDEOGRAPH-FA99：本机字体确实没有。
- U+FAAE — CJK COMPATIBILITY IDEOGRAPH-FAAE：本机字体确实没有。
- U+FAC3 — CJK COMPATIBILITY IDEOGRAPH-FAC3：本机字体确实没有。
- U+FAD9 — CJK COMPATIBILITY IDEOGRAPH-FAD9：本机字体确实没有。
- U+2F800 — CJK COMPATIBILITY IDEOGRAPH-2F800：本机字体确实没有。
- U+2F816 — CJK COMPATIBILITY IDEOGRAPH-2F816：本机字体确实没有。
- U+2F82D — CJK COMPATIBILITY IDEOGRAPH-2F82D：本机字体确实没有。
- U+2F843 — CJK COMPATIBILITY IDEOGRAPH-2F843：本机字体确实没有。
- U+2F85A — CJK COMPATIBILITY IDEOGRAPH-2F85A：本机字体确实没有。
- U+2F870 — CJK COMPATIBILITY IDEOGRAPH-2F870：本机字体确实没有。
- U+2F887 — CJK COMPATIBILITY IDEOGRAPH-2F887：本机字体确实没有。
- U+2F89D — CJK COMPATIBILITY IDEOGRAPH-2F89D：本机字体确实没有。
- U+2F8B4 — CJK COMPATIBILITY IDEOGRAPH-2F8B4：本机字体确实没有。
- U+2F8CA — CJK COMPATIBILITY IDEOGRAPH-2F8CA：本机字体确实没有。
- U+2F8F7 — CJK COMPATIBILITY IDEOGRAPH-2F8F7：本机字体确实没有。
- U+2F90E — CJK COMPATIBILITY IDEOGRAPH-2F90E：本机字体确实没有。
- U+2F925 — CJK COMPATIBILITY IDEOGRAPH-2F925：本机字体确实没有。
- U+2F93B — CJK COMPATIBILITY IDEOGRAPH-2F93B：本机字体确实没有。
- U+2F952 — CJK COMPATIBILITY IDEOGRAPH-2F952：本机字体确实没有。
- U+2F968 — CJK COMPATIBILITY IDEOGRAPH-2F968：本机字体确实没有。
- U+2F97F — CJK COMPATIBILITY IDEOGRAPH-2F97F：本机字体确实没有。
- U+2F9C2 — CJK COMPATIBILITY IDEOGRAPH-2F9C2：本机字体确实没有。
- U+2F9D9 — CJK COMPATIBILITY IDEOGRAPH-2F9D9：本机字体确实没有。
- U+2F9EF — CJK COMPATIBILITY IDEOGRAPH-2F9EF：本机字体确实没有。
- U+2FA06 — CJK COMPATIBILITY IDEOGRAPH-2FA06：本机字体确实没有。
- U+2FA1D — CJK COMPATIBILITY IDEOGRAPH-2FA1D：本机字体确实没有。

建议安装 [BabelStone Han](https://www.babelstone.co.uk/Fonts/Han.html)。下载副本中上述 27 项均已实测 FT 索引非零且能加载；未安装到系统，原矩阵仍反映原始本机状态。
验证字体 SHA-256：`d8bb747b3fdccd84a60bd0aa56bb90937270d0bd15f1101cd8f2a5a3709dd0a3`。

## 真实 EPUB 渲染

同一本确定性 EPUB 的四个 spine 文档各一页。纯白背景，720×720；非空白定义为任一 RGB 通道 <250，分母为整页 518,400 像素。
FT 零索引与 .notdef 统计覆盖每个可见输出字形；隐藏的连接符/选择符另在 640 项矩阵中逐个验证。

| 场景 | 截图 | 非空白比例 | FT 零索引 | .notdef |
|---|---|---:|---:|---:|
| chinese_emoji | [PNG](chinese_emoji-0.png) | 12.677469% | 0 | 0 |
| japanese | [PNG](japanese-0.png) | 10.583333% | 0 | 0 |
| arabic_rtl | [PNG](arabic_rtl-0.png) | 11.976080% | 0 | 0 |
| math_symbols | [PNG](math_symbols-0.png) | 7.422454% | 0 | 0 |

8 条 ZWJ 序列的输出字形 ID 均与独立 HarfBuzz/同一 Segoe UI Emoji 参考一致，FT 零索引及 .notdef 均为 0。
家庭 emoji 使用多枚定位组件，不能用“必须单字形”作为判定。`render-after.json` 同时保留原始字形及位置数据；此项结论是字形序列一致。
样本 EPUB SHA-256：`da3ce098c0098de162e636abfb3668817e2cf8cff81b80874016bcfcd1a002a0`；只提交生成脚本与哈希，EPUB 留在 build/。

## 回归

- 冻结修复前基线：`d9ffdbf09da654340bc35c043ad6d4b49cc344d1`。同一 19 本书、Reader.otf 字体和 tools/regress/layout.json。
- **19/19 成功，11,318 页，页数/字形数/每页像素 SHA-256 全部不变**；比较结果见 books.diff.json。
- 该既有真书回归入口使用 exr_font_open；管理器路径由矩阵、实际加载、EPUB 混排和 native-font-manager 测试覆盖。
- **ctest 228/228 全绿**（启用 EXR_BUILD_FUZZ）；层依赖检查通过。
- negative-control.txt：相同新增管理器回归对修复前 DLL 明确失败，对修复后 DLL 通过。

## 复跑

Windows / MinGW；原生依赖由项目 CMake 固定。Python 验收使用 stdlib 与本机已有的 uharfbuzz（仅序列参考）；无需安装字体。

```powershell
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DEXR_BUILD_FUZZ=ON -DEXR_ENABLE_ICC=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_MP3=OFF -DEXR_ENABLE_PDF_CRYPTO=OFF -DEXR_BUILD_JNI=OFF
cmake --build build -j 4
pwsh -File tests/build_font_coverage.ps1 -Build build
python tests/font_coverage.py matrix --dll build/libexreader.dll --freetype build/font_coverage_ft.dll --output build/fontcov-after --require-complete
python tests/font_coverage.py render --dll build/libexreader.dll --freetype build/font_coverage_ft.dll --output build/render-after --require-complete
ctest --test-dir build --output-on-failure -j 4
```
