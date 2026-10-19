# PDF 挖空透明组（工作包 1）设计与参考

状态：**已完成**（引擎、42 场景、嵌套语义、取消/预算/旧消费者回归、交替采样）。`EXR_GROUP_KNOCKOUT` 在
`canvas.c`/`blend.c` 生效，PDF的`K`映射和原输入生成器在3.33.1纠正（此前极性相反）；`tools/generate_knockout_fixtures.py` 生成
**50 个原创场景**（16 模式隔离、16 模式非隔离、10 个 alpha/coverage、6 个文字/图像/嵌套元素、
独立参考，`native-blend` 逐像素比对最大差 0。支持矩阵暂记“部分”，直到交替性能采样与全量 CI 记录补齐。

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
group_alpha = union(group_alpha, mask)
```

**常量 alpha 与覆盖率必须分开**：若把两者先乘成一个 mask 再代入 `P`，半覆盖边缘会二次衰减
（`0.25c + 0.75B0` 而不是 `0.5c + 0.5B0`）。当前 `exr_pixel_composite` 在 `blend.c:85` 已经
分别持有 `color&255` 与 `coverage`，实现时直接用这两个量。

## 3. 参考实现

`tools/pdf_group_reference.py` 的 `group(..., knockout=True)` 是 40 位 Decimal 独立实现；
`python tools/pdf_group_reference.py --self-test` 校验五条不变量：

1. 全覆盖探针上只剩最后一个有覆盖的元素，结果等于它与 B0 的合成；
2. 挖空与累积结果在元素重叠时不同；
3. 绘制顺序改变会改变挖空结果，但不改变组 alpha（alpha 是覆盖并集）；
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

下一步：

1. 生成 ≥32 个挖空场景与独立参考掩码（含 16 模式、路径/文字/图像/嵌套）；
2. ~~取消/abort/深度/预算与旧 sink 组合回归~~（已完成：预算 23/24 字节、取消、abort 无残留、32 层深度、无 begin_group 的消费者）；
3. 新旧交替性能采样，确认 24 B/px 与 64 MiB 上限未变；
4. 提交、推送、七作业 CI，更新 HANDOFF/VALIDATION/SUPPORT_MATRIX。
