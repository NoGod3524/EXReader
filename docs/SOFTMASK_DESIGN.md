# 图形状态软遮罩（工作包 2）设计

状态：**已实现并验收**。Alpha/Luminosity、`BC`、指数型 `TR`、`/Matrix`、`/BBox`、`q/Q`、`/None`、
DeviceGray 组色空间以及“遮罩作用于组提交”均可用；41 个场景与 8 个损坏输入进入 `native-blend`，
非 Identity/指数型的 `TR` 与非 RGB/灰组色空间明确返回 `EXR_UNSUPPORTED`。

## 1. 规范范围（ISO 32000-1 11.6.5.2）

`ExtGState` 的 `SMask` 是 `/None` 或软遮罩字典：

```
<< /Type /Mask /S /Alpha|/Luminosity /G <form XObject>
   /BC [c1 ... cn]   % 仅 Luminosity 使用，缺省 0
   /TR <function>    % Identity 或 1 输入函数，缺省 Identity
>>
```

- `G` 是透明度组 Form：其 `/BBox` 决定覆盖范围，`/Matrix` 把遮罩空间映射到**应用该遮罩时的
  用户空间**；`/Group` 的 `/CS` 决定亮度计算所用的组色空间。
- `Alpha` 取组结果的 alpha；`Luminosity` 先按 `BC` 与组色空间合成，再取亮度并送入 `TR`。
- `q`/`Q` 保存恢复图形状态；`gs` 换遮罩；`SMask /None` 清除。

## 2. 与已有图像 SMask 的区别

`/SMask` 图像（图像 XObject 的 `/SMask` 条目）是逐像素 alpha 图，已由 `pdf_image.c` 实现并有
`native-pdf-image` 回归。图形状态软遮罩是**参数化的 Form**，需要先渲染再作用到后续元素，
两者不共用代码，验证也分开：前者在 `native-pdf-image`，后者新增 `native-pdf-softmask`。

## 3. 实现路径

1. **解析**：`graphics_state()` 现在直接拒绝；改为解析字典并保存 `{id, kind, bc[4], bc_count, tr, matrix}`
   到 `exr_pdf_paint_state`。损坏输入（缺 `G`、`S` 非法、`BC` 个数与色空间不符、`TR` 不支持、
   循环引用、`BBox` 空）各有明确 `EXR_FORMAT`/`EXR_LIMIT`。
2. **渲染遮罩**：在 `gs` 生效时把 `G` 绘制到一张与页面同尺寸的离线画布（组隔离、自带 `BBox`
   裁剪），得到 RGBA；`Alpha` 取 alpha，`Luminosity` 先与 `BC` 合成再按 0.3/0.59/0.11 取亮度，
   经 `TR` 后得到 8 位遮罩。
3. **应用**：画布增加内部软遮罩状态（`mask` 位图 + 设备矩阵）。`exr_pixel_composite`、
   `exr_pixel_blend`、`exr_composite_compound` 与图像合成入口在写入前把覆盖率乘上遮罩值。
   遮罩在 `Q` 恢复或 `SMask /None` 时清除。
4. **计费**：遮罩缓冲为 1 字节/像素；离线画布按组预算计费，超过 64 MiB 返回 `EXR_LIMIT`。
   与挖空组的 24 B/px 分开记账。

## 4. 坐标与色空间

- 遮罩画布与页面同尺寸，`G` 的 `/Matrix` 与 `gs` 时的 CTM 共同决定最终设备变换；像素 (x,y)
  直接索引遮罩，不做二次重采样。
- 亮度计算用 `G` 组声明的 `/CS`（缺省为应用时的 DeviceRGB），`BC` 分量按该色空间解释；
  当前只支持 DeviceRGB/DeviceGray 组色空间，其他返回 `EXR_UNSUPPORTED`。

## 5. 验收映射

| 要求 | 落点 |
| --- | --- |
| Alpha、Luminosity 各 ≥16 场景 | `tools/generate_softmask_fixtures.py` + `native-pdf-softmask` |
| 含 `G`/`BC`/`TR` | 场景按 4 种 Mask 形状 × 4 种基色/BC × 2 种 TR 组合 |
| 矩阵/BBox | 每类含单位矩阵、平移、缩放与非满幅 BBox |
| 嵌套、q/Q/None 恢复 | 遮罩内再套遮罩、`Q` 后遮罩失效、显式 `/None` |
| ≥8 损坏输入 | 缺 `/G`、`/S` 未知、`/BC` 长度错误、`TR` 不是函数、循环、超预算、空 BBox、非 Form |
| 与图像 SMask 分开 | 独立测试与独立夹具目录，不复用图像 SMask 的期望 |
| 源坐标、组色空间 | 亮度场景用非 RGB 组色空间（DeviceGray）与偏移矩阵核对像素位置 |

## 6. 下一步

1. 解析与拒绝矩阵（先做损坏输入，保持默认拒绝）；
2. 离线渲染 `G` + Alpha 路径；
3. Luminosity + BC + TR；
4. 画布合成入口接入遮罩；
5. 场景矩阵与 120 项回归、七作业 CI。
