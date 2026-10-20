# PDF 挖空透明组（工作包 1）设计与参考

状态：核心机制已有实现，源alpha与嵌套裁小在3.34.1修复；128个新嵌套探针与Decimal参考
最大差1/255，MuPDF1.28.2低alpha部分组合仍有最大11/255差异，未宣告完整对齐。
原50场景与像素期望保留，K字面极性已在3.33.1纠正。

## 1. 语义（ISO 32000-1 11.4.5）

挖空组（knockout group）与普通组的唯一区别：**每个元素与组的初始 backdrop 合成，而不是与
已累积的结果合成**。元素重叠时，后绘制的元素在其覆盖区内替换先前的元素，而不是叠加。

- 透明组字典的`K`：`true` = 挖空，`false` = 不挖空（默认`false`）。这与ExtGState中的文字挖空`TK`是不同属性。
- 与 `I`（隔离）正交，四种组合都存在；页面总是隔离，Form/AP 的 `I` 缺省 `false`。
- 组自身的 alpha/混合/裁剪在提交时仍只应用一次；非隔离组仍做背景移除。

## 2. 每像素规则

设初始 backdrop 为 `B0`（隔离组为全透明），元素常量 alpha 为 `a`、几何覆盖率为 `c`、
混合模式为 `m`：

```
mask = a * c
P    = over(B0, source, a, m)        # 元素只与 B0 合成
out  = c * P + (1 - c) * current     # 覆盖区内是 P，区外保留当前结果
group_alpha = c * a + (1-c) * previous_group_alpha
```

**常量 alpha 与覆盖率必须分开**：若把两者先乘成一个 mask 再代入 `P`，半覆盖边缘会二次衰减
（`0.25c + 0.75B0` 而不是 `0.5c + 0.5B0`）。当前 `exr_pixel_composite` 在 `blend.c:85` 已经
分别持有 `color&255` 与 `coverage`，实现时直接用这两个量。

## 3. 参考实现

`tools/pdf_group_reference.py` 的 `group(..., knockout=True)` 是 40 位 Decimal 独立实现；
`python tools/pdf_group_reference.py --self-test` 校验五条不变量：

1. 全覆盖探针上只剩最后一个有覆盖的元素，结果等于它与 B0 的合成；
2. 挖空与累积结果在元素重叠时不同；
3. 全几何覆盖时，组自身alpha跟随后一个有效元素；背景alpha不算作源alpha；
4. 零覆盖元素不会把组结果倒回 backdrop；
5. 隔离挖空的初值是透明，组色即元素本色（未预乘）。

现有 208 个混合样本与 160 个组探针未受影响，加入挖空后仍全部重现。

## 4. 内部表示：不需要新缓冲

关键观察：`exr_composite_initialize`（`blend.c:90`）已经把父 bitmap 复制给孩子，并保留
`state->backdrop = *parent`；`read_rgba` 在 `p[4]==0` 时回退到 backdrop。也就是说**初始
backdrop 本来就一直可读**，挖空不需要额外的整画布缓冲。

| 方案 | 每像素 | 1000×1500 单组 | 结论 |
| --- | ---: | ---: | --- |
| 现有非隔离组（RGBA8 + 5 float） | 24 B | 36 MB | 保持 |
| 挖空组（复用同一结构 + 1 个标志位） | 24 B | 36 MB | **采用** |
| 另存 8 位 B0 副本 | 28 B | 42 MB | 不必要 |
| 另存 5 float B0 | 44 B | 66 MB（超 64 MiB） | 排除 |

实现落点：`exr_composite_state` 加 `unsigned knockout`；`exr_pixel_composite` 内分支；
`exr_canvas_begin_group` 接受 `EXR_GROUP_KNOCKOUT`；`EXR_GROUP_ISOLATED|EXR_GROUP_KNOCKOUT`
可组合。公共 sink 的 `begin_group` 已带 `flags`，ABI 不变。

## 5. 验收映射（工作包 1）

| 要求 | 落点 |
| --- | --- |
| ≥32 个原创场景，覆盖隔离/非隔离 × 16 模式 × 路径/文字/图像/嵌套 | `tools/generate_pdf_blend_fixtures.py` 扩展 + `tests/fixtures/pdf-blend/` |
| 内部实色探针预乘差 ≤3/255 | 参考探针（40 位 Decimal）与引擎 RGBA8 对比；50 个场景实测差 0 |
| shape 与透明度区别 | 场景里同时放全覆盖实心块与 50% 常量 alpha 块 |
| 取消/abort/深度/预算/旧 sink 回归 | 复用 `exr_canvas_end_layer` 失败路径与现有 32 层、64 MiB 用例 |
| 不能拿“清空背景”冒充挖空 | 反向用例：单元素挖空结果必须等于普通绘制；两元素重叠必须不同 |

## 6. 边缘采样口径

抗锯齿边缘不参与 ≤3/255 的逐像素比较：参考模型只描述整数覆盖，边缘覆盖率是引擎栅格化的
结果，两者本就不可能逐位相同。正式口径分两层：

- **内部全覆蓋像素**：逐通道（预乘与非预乘两种输出）差必须 ≤3/255，当前 50 个场景实测为 0；
- **半覆蓋边缘**：由既有的路径/字形抗锯齿回归（`native-vector`、`native-pdf-graphics`）保证。
  挖空只改变合成操作数，不改变覆盖率本身，因此边缘正确性不需要在这组场景里重复建模。
  `knockout-edges` 用半像素偏移的矩形产生真实边缘，掩码只取内部 3..12 的像素。

## 7. 实施记录与下一步

已完成：`blend.c` 的挖空像素路径与组 alpha 替换、`canvas.c` 的组状态与预算、
`pdf_content.c`/`pdf_annotation_paint.c` 的 `K` 映射、`tests/test_blend.c` 的六个挖空用例。
实施中发现两处必须坚持的细节：

- 挖空必须**同时替换覆盖度**，否则非隔离组在透明背景上会把 50% 元素当成不透明；
- 3.33.1发现此前PDF映射与生成器共同把K极性写反；现已改为true挖空、false/缺省普通组，50个场景的输入PDF重新生成，独立Decimal像素期望保持不变。

历史下一步（实际最新进展见末尾）：

1. 生成 ≥32 个挖空场景与独立参考掩码（含 16 模式、路径/文字/图像/嵌套）；
2. ~~取消/abort/深度/预算与旧 sink 组合回归~~（已完成：预算 23/24 字节、取消、abort 无残留、32 层深度、无 begin_group 的消费者）；
3. 新旧交替性能采样，确认 24 B/px 与 64 MiB 上限未变；
4. 提交、推送、七作业 CI，更新 HANDOFF/VALIDATION/SUPPORT_MATRIX。


## 3.34.1：源alpha与嵌套修正

旧代码把非隔离挖空组的完整alpha（含背景）写进组自身alpha；普通组的并集式更新也被
错误用于复合路径/组提交。现统一按几何shape替换源alpha，RGBA/CMYK/填描合并共用规则。
非隔离子组移除其实际初始背景，挖空父组中子组的初始背景不再使用父组已绘制像素。
隔离挖空父组提供透明初值；非隔离挖空父组的背景坐标逐层相加。

修正`pdf_group_reference.group`的错误alpha并集公式，并修正旧生成器中对背景alpha的
混淆。已有50场景输入、mask和RGBA期望均逐字节重现，不改旧golden来容纳实现。
新128份PDF跨父/子隔离、两种背景alpha与16模式。内部预乘/白底共1024个通道参考。
独立MuPDF差异逐场景保存，低alpha子集仍待深入核验，不扩大3/255内部阈值。

嵌套组和AP按clip裁小，24组RGB/CMYK、隔离/非隔离/挖空、变换/软遮罩/丢弃与整图
逐字节一致，工作分配至少降低97%；1000次嵌套创建/提交/丢弃后内存恒定。


## 3.34.2：遮罩作用域与组形状修复（2026-10-19）

ExtGState缺省/null的SMask保留当前值，显式None才清除。透明Form内部重置SMask，
外部遮罩在整组提交时应用一次；画布组进入/退出保存、恢复并释放各自遮罩。
组在挖空父级内单独累计几何shape，半像素边缘不再作为全覆盖低opacity替换。
shape平面仅在挖空/shape父级需要时分配，每像素4字节，计入层预算及内存报告。
PDF绘制器存活遮罩聚合限制64MiB；嵌套遮罩共享绘制工作计数，逐行检查取消和预算。

27个正常场景与3个拒绝输入；独立数学探针最大差1/255，3.34.1最大差144/255。
MuPDF1.28.2内部探针最大差5；半覆盖边缘差41单独归类，不扩大内部容差。
GCC/MSVC各139/139、ICC-OFF6/6、安装组件4/4及13头C++独立编译通过；
EXACT C++实际运行3.34.2 ABI1，703项布局逐行不变，两个DLL均305导出。
分层99对象/1026符号引用/898include，无逆向。

AIS、图像shape/opacity与自身mask覆盖图形状态mask仍需审计，WP1/WP2尚未整包关闭。
证据：[汇总](validation/2026-10-19-mask-scope.json)、[逐场景对照](validation/2026-10-19-mask-scope-reference.json)。


## 3.35.1：几何覆盖率与递归遮罩预算（2026-10-19）

CMYK路径不再把几何覆盖率预乘进常量alpha；图像在需要shape的组内分别累计
矩形采样覆盖与样本透明度。普通无shape路径保留原取整，无额外像素缓冲。
48个RGB/CMYK、路径/图像、直接/隔离子组/非隔离子组、半透明/不透明、
半边/四分之一角组合按独立合成公式验收。旧3.35.0在最小图片半边输入上
绿色通道191，期望64；新回归通过，未修改已有golden。

此前64MiB仅在单个PDF绘制器内计数，递归G会新建绘制器且绕开父计数。
现在所有递归G共享活跃mask字节数，渲染G前预留其结果空间，失败/提交/丢弃归还。
以60MiB预留、64MiB及64MiB+1验证预算错误先于深度错误，失败后计数完整恢复，输出为空。
此64MiB限制针对mask结果载荷，不代表所有画布/字体/图像工作内存的总和。

GCC/MSVC各140/140，ICC-OFF8/8；安装组件4/4、13头C++与EXACT3.35.1实际运行通过。
703项ABI逐行不变，两个DLL均305导出；分层99/1035/899，逆向0。
[原始汇总](validation/2026-10-19-coverage.json)。核心/PDF3.35.1，其余3.33.0。
AIS、图片内在shape与mask/opacity、外部参考差异仍继续，未关闭整个WP1/WP2。


## 3.36.0：通用alpha源与PDF AIS（2026-10-19）

版本化sink尾追加`alpha_source(context, flags, error)`：`EXR_ALPHA_CONSTANT_SHAPE`
把常量alpha与图形状态mask作为shape，缺省作为opacity；`EXR_ALPHA_IMAGE_SHAPE`
把bitmap alpha作为图片内在shape。显式图片mask始终限制shape，soft mask遵循AIS。
图片矩形几何覆盖、采样alpha、mask与常量分别处理，不再把所有alpha混成shape。
路径/文字、复合填描、RGB/CMYK和组提交复用该规则；透明Form仍只在外部应用一次状态。
保存/恢复、组进入/退出与标注/page包装sink完整转发。旧消费者可保留原图片解释，
请求constant-shape而缺少回调时明确拒绝，截断非零指针与错误回调均有回归。

166份原创正常PDF、4份错误AIS值，含16模式和8类绘制、q/Q/缺省/null；
192个公开画布组合覆盖RGB/CMYK、路径/图片、直接/隔离子组/非隔离子组、
两种alpha与两种边缘、AIS/软mask开关。旧golden未改，普通图片不新增像素平面。
GCC/MSVC各141/141，ICC-OFF9/9，安装组件4/4，13头C++与EXACT3.36.0运行通过。
703项公开测量仅版本化sink总大小128→136，全部旧偏移保持；两个DLL均305导出。
分层99对象/1039符号引用/899include，逆向0。当前核心/PDF3.36.0，其余3.33.0。
[本地记录](validation/2026-10-19-alpha-source.json)、[逐场景参考](validation/2026-10-19-alpha-source-reference.json)。
MuPDF/Poppler的opacity-mask、图片采样及复合填描差异单独保留，内部容差未放宽。
