# PPTX-M6b 验收报告

最终矩阵 exit 0：15/15 文件通过，12 份有效件页数一致，31/31 页 coverage、color=12/12、text 全部通过；3 份坏件均为 EXR_FORMAT(5)。
CTest **551/551** 通过，仅排除 sdk-release、sdk-doc-coverage，包含 sdk-release-checker；原 M2–M5 **67/67** 通过。

## 覆盖率定义与分类代码

逐个叶形状及表格单元断言，组容器不重复计数。总计 203 个区域：{'text': 84, 'filled': 114, 'outline': 5}。

| 分类 | 判定，容差 4px |
|---|---|
| filled | 去文字位图 − 仅背景位图的墨迹 bbox 覆盖原几何 bbox |
| text | 原位图 − 去文字位图的字形像素 >0，字形 bbox 在原形状 bbox 内 |
| outline | 形状 bbox 的 4px 邻域中存在非背景像素 |

普通形状读取 `shape.fill.type`，单元格读取 `cell.fill.type`，图片作为 PICTURE；解析到主题填充的形状也归为 filled。分类原码：

```python
@property
def coverage_kind(self):
    # Lines use paint for their stroke, not for an area fill. The resolved
    # paint also handles inherited theme fills (fill.type is then None).
    filled = self.fill_type in (MSO_FILL_TYPE.SOLID, MSO_FILL_TYPE.GRADIENT, MSO_FILL_TYPE.PICTURE)
    if self.geometry != 'line' and (filled or self.paint is not None):
        return 'filled'
    return 'text' if self.text else 'outline'
```

`without_text()` 保留填充、边框和几何；`without_shapes()` 保留原背景、主题和关系。
字形像素按最近文本框归属，保留框外像素以检测溢出；每框均检查文字存在性。
逐形状的 name/kind/expected_bbox/actual_bbox/glyph_pixels/ok 写入 [matrix.json](matrix.json)。
白图、16px 错位、错色、文字丢失、文字溢出、边框丢失和彩色背景冒充墨迹的故障注入均正确失败，见 [oracle.txt](oracle.txt)。

原 12 点颜色算法、位置、每通道容差 4 和至少 10/12 门槛保持；全部 372 个采样坐标及预期 RGB 与 6c57460d 一致，见 [sample-invariance.txt](sample-invariance.txt)。
宿主字体回退/缺字警告可接受，混合及其他警告仍失败。

## p:bg 实现与四种形态实测

背景先于形状绘制，顺序 slide → layout → master → 白底。
纯色、渐变、图片复用 M3 的 color/gradient_fill/gradient_ramp/image_fill/texture_draw，主题引用绑定 schemeClr/phClr。

| 形态 | 点与实际 RGB |
|---|---|
| solidFill #123456 | (0,0)、(719,0)、(0,539)、(719,539)、(360,270) 均 (18,52,86)；前景 (100,80) 为 (0,255,0) |
| gradFill 红→蓝，0° | y=270，x=0/180/360/540/719： (255,0,0) / (191,0,64) / (127,0,128) / (64,0,191) / (0,0,255) |
| blipFill 红蓝图片 | (0,0)、(180,270) 为 (255,0,0)；(539,270)、(719,539) 为 (0,0,255) |
| bgRef idx=1002 + accent2 | (0,0)、(360,270)、(719,539) 均 (194,58,85)；改 accent3 为 (53,121,189) |

idx=1001 为 (255,0,0)，idx=1003 主题渐变中心为 (97,29,170)；idx=0/1000 白底且无警告。
0°/45°/90°/180°/270° 背景渐变均与同尺寸形状渐变逐像素一致。
母版纯色 (91,36,109)、母版图片 (37,158,213)、版式优先级、显式白背景覆盖及无背景白底均通过。
完整 stdout：[backgrounds.txt](backgrounds.txt)。新增 5 份确定性合成 PPTX，重生成检查通过。

## 31 页全量输出

```text
bullets.pptx#1 coverage=ok color=12/12 text=ok
chinese.pptx#1 coverage=ok color=12/12 text=ok
gradient-alpha.pptx#1 coverage=ok color=12/12 text=ok
image-text.pptx#1 coverage=ok color=12/12 text=ok
merged-table.pptx#1 coverage=ok color=12/12 text=ok
nested-groups.pptx#1 coverage=ok color=12/12 text=ok
standard-4x3.pptx#1 coverage=ok color=12/12 text=ok
theme-accents.pptx#1 coverage=ok color=12/12 text=ok
title.pptx#1 coverage=ok color=12/12 text=ok
twenty.pptx#1 coverage=ok color=12/12 text=ok
twenty.pptx#2 coverage=ok color=12/12 text=ok
twenty.pptx#3 coverage=ok color=12/12 text=ok
twenty.pptx#4 coverage=ok color=12/12 text=ok
twenty.pptx#5 coverage=ok color=12/12 text=ok
twenty.pptx#6 coverage=ok color=12/12 text=ok
twenty.pptx#7 coverage=ok color=12/12 text=ok
twenty.pptx#8 coverage=ok color=12/12 text=ok
twenty.pptx#9 coverage=ok color=12/12 text=ok
twenty.pptx#10 coverage=ok color=12/12 text=ok
twenty.pptx#11 coverage=ok color=12/12 text=ok
twenty.pptx#12 coverage=ok color=12/12 text=ok
twenty.pptx#13 coverage=ok color=12/12 text=ok
twenty.pptx#14 coverage=ok color=12/12 text=ok
twenty.pptx#15 coverage=ok color=12/12 text=ok
twenty.pptx#16 coverage=ok color=12/12 text=ok
twenty.pptx#17 coverage=ok color=12/12 text=ok
twenty.pptx#18 coverage=ok color=12/12 text=ok
twenty.pptx#19 coverage=ok color=12/12 text=ok
twenty.pptx#20 coverage=ok color=12/12 text=ok
upstream-font-color.pptx#1 coverage=ok color=12/12 text=ok
wide-16x9.pptx#1 coverage=ok color=12/12 text=ok
```

原始命令输出：[matrix.txt](matrix.txt)。所有页面的原位图、去文字位图、仅背景位图在 `build/pptx-m6/pptx-real-m6b-results/`。

## gradient-alpha：12/12 实际 RGB

| 坐标 (x,y) | 实际 RGB | 预期 RGB | 最大通道误差 |
|---|---|---|---:|
| (394,345) | (91, 113, 126) | (91, 113, 126) | 0 |
| (521,390) | (75, 124, 158) | (75, 124, 158) | 0 |
| (815,358) | (93, 146, 141) | (93, 146, 142) | 1 |
| (454,415) | (38, 140, 158) | (38, 140, 158) | 0 |
| (48,459) | (212, 231, 242) | (212, 231, 242) | 0 |
| (265,345) | (202, 162, 125) | (201, 162, 125) | 1 |
| (448,390) | (78, 126, 159) | (78, 126, 159) | 0 |
| (737,358) | (99, 150, 144) | (99, 150, 145) | 1 |
| (301,415) | (37, 120, 147) | (37, 120, 147) | 0 |
| (912,459) | (94, 150, 186) | (94, 150, 186) | 0 |
| (136,345) | (209, 168, 128) | (209, 168, 128) | 0 |
| (485,390) | (76, 125, 159) | (77, 125, 159) | 1 |

12/12 通过，最大通道误差 1。机器可读：[gradient-alpha-rgb.tsv](gradient-alpha-rgb.tsv)。

## 20 页耗时

每页 5 次，共 100 次，测量公共 `exr_fixed_render`，包含位图分配，不含 Python 拷贝与 oracle；最终矩阵独立运行。

| 版本 | 中位数 ms | 最大值 ms |
|---|---:|---:|
| 首版 M6 记录 | 20.531 | 47.197 |
| 本次改动前，同机复测旧 DLL | 18.871 | 33.005 |
| 最终 M6b | 17.887 | 40.318 |

最终中位数为首版的 **0.871 倍**，低于 1.5 倍门槛 30.75ms；原最大值 <200ms 门槛仍保留。

实测整页背景的通用扫描器增加约 12.491ms，见 [background-cost.txt](background-cost.txt)。
`src/vector.c` 对整数对齐、完整四边闭合、不透明 RGBA、Normal、无 composite/CMYK 的矩形直接填像素，保留裁剪、逐行取消及原工作量计数。
360 组与拆分成 5 条边的原扫描器逐像素对照通过，含透明底、部分裁剪、反向、偏移、退化及非矩形。

## 严格文字几何与回归记录

上游原件的 `+mn-lt` 实际指向已安装的 Calibri。补齐 +mj/+mn 的 lt/ea/cs 主题字体解析后，两个长框的字形右端从 499px 回到 479px，原框右端为 492/491px，保持 4px 判据。
六个主题字体槽位与显式实际族名的位图相同；未安装的实际族名仍报告字体回退，见 [theme-font.txt](theme-font.txt)、[upstream-font.txt](upstream-font.txt)。

```powershell
$env:PYTHONUTF8 = '1'
python tests/pptx_real_matrix.py --library build/pptx-m6/libexreader.dll --output build/pptx-m6/pptx-real-m6b-results
ctest --test-dir build/pptx-m6 --output-on-failure -j 4 -E '^(sdk-release|sdk-doc-coverage)$'
pwsh -NoProfile -File 'C:\Users\Oscar\OneDrive\Desktop\deepseekHarness\ops\prepush-check.ps1' -Worktree 'C:\Users\Oscar\Documents\Codex\EXReader-pptx-m6'
```

CTest 矩阵设 RUN_SERIAL，性能测量不与其他 CTest 竞争；PYTHONUTF8=1 用于既有非 ASCII 文件读取。
[ctest-all.txt](ctest-all.txt)、[ctest-results.xml](ctest-results.xml)、[prepush.txt](prepush.txt) 均为最终通过结果。
`tests/check_reading_release.py` 逐字节未变，SHA-256：`6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b`。
库 SHA-256：`2e176f40c7741d1f26af8d46a5c8b227314e67e2d2b4ab5f423fb93530f8e145`。结构化汇总：[verification-summary.json](verification-summary.json)。
