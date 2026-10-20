# WP7：其他文字脚本交接记录

更新日期：2026-10-20。分支 `codex/wp7-scripts`，基线提交 `2454848`。
本包只声明下列八个脚本；其他 WP 的状态不变。

## 1. 逐脚本状态

| 脚本 | 塑形 | 真实字体 | 合成字体 | 50 序列 | glyph 差异 | 最大 advance/offset 差异 @200px |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Bengali | 支持 | Noto Sans Bengali 未修改 | `beng-synthetic.ttf` | 50 + 50 | 0 | 1.2 px |
| Tamil | 支持 | Noto Sans Tamil 未修改 | `taml-synthetic.ttf` | 50 + 50 | 0 | 1.2 px |
| Telugu | 支持 | Noto Sans Telugu 未修改 | `telu-synthetic.ttf` | 50 + 50 | 0 | 0.8 px |
| Kannada | 支持 | Noto Sans Kannada 未修改 | `knda-synthetic.ttf` | 50 + 50 | 0 | 1.4 px |
| Malayalam | 支持 | Noto Sans Malayalam 未修改 | `mlym-synthetic.ttf` | 50 + 50 | 0 | 1.2 px |
| Thai | 支持 | Noto Sans Thai 未修改 | `thai-synthetic.ttf` | 50 + 50 | 0 | 1.4 px |
| Khmer | 支持 | Noto Sans Khmer 未修改 | `khmr-synthetic.ttf` | 50 + 50 | 0 | 1.0 px |
| Myanmar | 支持 | Noto Sans Myanmar 未修改 | `mymr-synthetic.ttf` | 50 + 50 | 0 | 0.8 px |

“支持”指：有脚本专用分类/重排、固定 50 序列真实与合成字体对照、取消/超限/失败清理、
双向/字素断行/回退/选文/分页随机恢复回归；边界见第 5 节。

## 2. 脚本配置

实现位于 `src/opentype.c`，没有新增 ABI 或 schema。Indic 脚本共用一套按
USP10/HarfBuzz 顺序的 GSUB 阶段；Thai/Khmer/Myanmar 使用独立重排。

| 脚本 | modern / old tag | virama | reph 位置 | reph 模式 | blwf 模式 |
| --- | --- | --- | --- | --- | --- |
| Devanagari（既有） | `dev2` / `deva` | 094D | before-post | implicit | pre+post |
| Bengali | `bng2` / `beng` | 09CD | after-subjoined | implicit | pre+post |
| Tamil | `tml2` / `taml` | 0BCD | after-post | implicit | pre+post |
| Telugu | `tel2` / `telu` | 0C4D | after-post | explicit | post-only |
| Kannada | `knd2` / `knda` | 0CCD | after-post | implicit | post-only |
| Malayalam | `mlm2` / `mlym` | 0D4D | after-main | log-repha | pre+post |
| Thai | `thai` | — | — | — | — |
| Khmer | `khmr` | 17D2（coeng） | before-subjoined | implicit | pre+post |
| Myanmar | `mym2` / `mymr` | 1039 | after-main | implicit | pre+post |

Indic 路径覆盖：新旧 spec 选择、分类（ISC/IPC + 脚本例外）、音节切分、
reph、pre-base matra 重排、pref、half/blwf/abvf/pstf、旧 spec halant、
标量分解（09CB/09CC、0BCA–0BCC、0C48、0CC0/0CC7/0CC8/0CCA/0CCB、
0D4A–0D4C）、ZWJ/ZWNJ、GPOS 标记附着。

Thai：`U+0E33/U+0EB3` 分解为 NIKHAHIT + SARA AA，并把 NIKHAHIT 越过
连续上方标记放到前面；簇范围合并。Khmer：Coeng+Ra 前置为 `pref`、
左元音前移、`cfar`、`clig`。Myanmar：Kinzi(`Ra As H`)、medial
Ya/Ra/Wa/Ha/Mon La、前后元音、asat 堆叠按 Myanmar 位置排序。

## 3. 字体来源、许可与散列

真实字体为 Google Fonts 的未修改 Noto Sans 变量字体，SIL Open Font
License 1.1；完整许可 `licenses/noto-sans-test-fonts.txt`。合成字体为
`tools/generate_wp7_test_fonts.py` 生成的原创矩形字体，MIT。

| 文件 | SHA-256 |
| --- | --- |
| `beng-real.ttf` | `dcd42978094e584a849c84a51450eeac40c8826057d566ea6d4b9627a403a05a` |
| `beng-synthetic.ttf` | `96b3202be9f63a93af881e074847c6bc60a1952b908ff5af66fef1f7ab5da613` |
| `taml-real.ttf` | `aa3a9b321f4b0bb2c40203ffbde9af89713227866e0e13f76e5b9eeea727cf88` |
| `taml-synthetic.ttf` | `77e1605066f60f035d2d73813014bdff6cfba5950025c548d61703d5e07d0c60` |
| `telu-real.ttf` | `e618af7bf999df192ed4f388eba2e563f2b5015034e9cbb317b5bd793bd7334d` |
| `telu-synthetic.ttf` | `a7e95534e152b51f3d6597af7e396a246869202d295d845bf512c91c9fb7d6b2` |
| `knda-real.ttf` | `cca4f3b3a8cb12fb261f1b43baf5d2f7f59d90fe123d41f0065ed3a183997ec9` |
| `knda-synthetic.ttf` | `c36b0327d1c09f87548d8b9abe61544eeecc5fd878168db07b514741eae557dd` |
| `mlym-real.ttf` | `312e0e7c3cc15fa09eb42a8f749eeb246b593ed420e3c81aafe8d910c3a6fb56` |
| `mlym-synthetic.ttf` | `88bcde6bcd0d575b39fbba404e57c35312eb5715292a70142e71538faf0cd74f` |
| `thai-real.ttf` | `5a1c559bb539583c8a1fd99d1c5b9491e5e14478c9cd2bd0970d5c3096cc9ef8` |
| `thai-synthetic.ttf` | `923470cd65bb7617daaf5a1ca7a3b2cfb934bc19ab9493c99d3353f5cb7786f6` |
| `khmr-real.ttf` | `f37a8431a0c5d5ed2f81a767417546aca576a81fb7eff9c924d46aecf828f2ca` |
| `khmr-synthetic.ttf` | `e3ea13ad2775ee4c3807ee3039c226b5b4b5020ed6703172ddd08dc51162ea96` |
| `mymr-real.ttf` | `7abbbfbe2514105d7ce94937aee3feb2ba89b73a256c8b77b5866bd9b83e32ec` |
| `mymr-synthetic.ttf` | `4c5a4a89c1ec2ce57046f6f9910bf140f8823cc9894b3afdb09ed08b418242c6` |

## 4. HarfBuzz 对照口径

参考由固定 HarfBuzz 14.6.0（uharfbuzz 0.56.3）生成，HarfBuzz 只用于开发期
生成 `tests/fixtures/wp7/reference.h`，**不是 EXReader 运行依赖**，不进入 SDK
链接或安装产物。

- 每个用例在 200 px 下比较 glyph id、cluster、advance/offset。
- HarfBuzz 使用 `REMOVE_DEFAULT_IGNORABLES`；EXReader 侧过滤
  `EXR_GLYPH_HIDDEN`。
- cluster：EXReader 公开接口给的是音节/字素组 UTF-8 范围，HarfBuzz 给每个
  glyph 的最小源 cluster start。两者不是同一粒度。测试要求
  `EX start <= HB cluster_start < EX end`，且 EX 范围单调、非空；不要求
  range end 相同。cluster 数值不是 OpenType 规范规定，属引擎映射策略。
- advance/offset：固定 1.5 px @200 px 容差。FreeType 返回整数 hinted
  advance，HarfBuzz 返回未 hint 的 font-unit 缩放值；本语料实测最大
  1.4 px（7 font units），glyph 序列 0 差异。没有为了提高通过率放宽 glyph
  或删除困难序列。

## 5. 已知边界

- 未实现 Thai/Lao 旧字体 PUA fallback（仅做 Unicode SARA AM 分解）；Noto
  等带 Thai GSUB 的字体不受影响。
- Khmer/Myanmar 的 broken cluster 当前不自动插入 dotted circle；固定 50
  序列不含孤立组合标记。
- Malayalam `U+0D4E` dot repha 的排序与 HarfBuzz 一致，但 GPOS y offset
  仍有一次差异（不在固定 50 序列中）；作为后续修正项保留。
- 未实现 Zawgyi、Sinhala、Gurmukhi/Gujarati/Oriya 的专属验收；本包只声明
  第 1 节八个脚本。
- 未改 ABI1/schema6、未改公开结构布局、未改全局版本；HarfBuzz 不进入运行依赖。

## 6. 复现

```sh
cmake -S . -B C:/Users/Oscar/exr-wp7-build -DCMAKE_BUILD_TYPE=Release
cmake --build C:/Users/Oscar/exr-wp7-build --config Release --parallel 8
ctest --test-dir C:/Users/Oscar/exr-wp7-build -C Release --output-on-failure
```

WP7 专项：

```sh
ctest --test-dir C:/Users/Oscar/exr-wp7-build -C Release -R native-wp7 --output-on-failure
python tools/wp7_sequences.py tests/fixtures/wp7/cases.json
python tools/generate_wp7_test_fonts.py
python tools/generate_wp7_reference.py
```

结果与散列见 `docs/validation/wp7-windows.json`。
