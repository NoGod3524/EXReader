# 软遮罩语义与外部差异

3.35.0，ABI1。规范来源：[ISO 32000-1:2008](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/PDF32000_2008.pdf)。
以下为已冻结的探针口径，完整WP1/WP2仍未验收。

## 实现与规范映射

| 项目 | 依据 | 当前回归 |
| --- | --- | --- |
| TR接受一输入、一输出；最终限制[0,1] | 表144、7.10；复用现有Type 0/2/3/4解析、求值与限额 | 42个Alpha/Luminosity函数场景、8个错误输入 |
| 透明Form内部重置SMask，外部整组应用一次 | 11.6.6，印刷页351 | `native-mask-scope` |
| 变换BBox限制G的绘制，而非外接轴对齐矩形 | 8.10、11.6.5.2，印刷页347 | 两类旋转探针；故意让内容溢出BBox |
| G保持自身K/I；Luminosity先在BC上计算组结果，再取亮度 | 11.5.2–3，印刷页342–343 | 挖空、非隔离Multiply与BC探针 |
| 软遮罩根可声明非隔离CS，不从调用页继承 | 表147，印刷页350 | 非隔离DeviceRGB亮度组 |
| 图像SMask优先于Mask；图像字典遮罩覆盖图形状态SMask | 11.6.4.3，印刷页345 | 18个图像组合探针，部分与外部引擎存在差异 |
| Alpha在BBox外取TR(0)，Luminosity取TR(BC亮度) | 11.6.5.2，印刷页346 | 完全离开画布的G和反相TR |

TR并未新增解释器或运行时依赖；已有PDF函数求值器限制图深、节点、数据和运算量。
所有转换费用进入与绘制共享的工作计数，失败输出为空。

## 独立对照

72个输入在透明预乘与白底各有4通道解析期望，共576个通道。当前最大差0/255。
旧3.34.2有44次渲染拒绝（透明/白底各记一次）；其成功渲染中的最大差191/255，
拒绝项单列，不能把缺失结果计作零误差。

[逐场景数据](validation/2026-10-19-mask-functions-reference.json)保留MuPDF1.28.2和
Poppler26.07.0的实际输出、版本及分类误差。白底Poppler通过独立进程直接绘制；
MuPDF透明输出使用其原生预乘像素。固定探针为(8,8)，边缘采样不参与此组。

| 待核验差异 | MuPDF相对解析期望最大差 | Poppler白底最大差 |
| --- | ---: | ---: |
| 图像显式Mask与图形状态SMask同时存在 | 0 | 191 |
| 可见色键Mask与图形状态SMask同时存在 | 194 | 191 |
| Alpha的G完全离开画布，TR为反相 | 255 | 255 |
| 非隔离亮度组在BC=.5上用Multiply绘制红色 | 41 | 39 |
| 旋转BBox外、其外接矩形内 | 0 | 128 |
| G本身为挖空组 | 3 | 96 |

以上差异保持开放，后续需核对其他实现与规范勘误，尤其是色键是否应作为固有shape继续
接受图形状态软遮罩。不能据本批内部探针吻合宣称达到MuPDF/Poppler的整体兼容深度。

复现：

```sh
python tools/generate_mask_function_fixtures.py
python tools/validate_nested_groups.py /path/to/library --manifest mask-function-manifest.json --poppler --output report.json
```

后续：AIS、图片固有shape与mask/opacity的分离、更多组色空间和全库安全审计。
