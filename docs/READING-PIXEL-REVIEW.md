# 固定 W9 差分图审阅记录

这份记录只登记已查看图像中的差分现象，`render_parity_granted=false`。没有冻结外部像素容差，
不据此授予 R3 整包或 PDF 正确性验收。

## 原始输入身份

- 原受测源码：`c6f0ba92321a284490a81a2bb355557803c17ec9`。
- 原运行：[39889934254](https://github.com/NoGod3524/EXReader/actions/runs/39889934254)，attempt 1；整轮因其他真实文件失败而未通过。
- 原工件：`reading-real-39889934254-1`，ID `12474462154`，23,861,710 字节。
- 原 ZIP SHA-256：`b677a592fa31171a758820d3beba732986419d8fc2af303e113e4e933da7f837`。
- 原件：唯一真实清单 `tools/reading_corpus/real-v1.json` 中 `irs-w9`；原件 SHA-256
  `2d420cbb4123dcf1fb82595b2359cfbb5d81f00b9df9d359fcc7af361d093f53`。

云端诊断先核完整 ZIP digest，再核报告中的每份 native/reference PPM 散列，保持 72 dpi、
612×792 像素、白底。MAE 在未量化原图上计算；contact sheet 的灰度量化只用于图像查看。

| 原页（零起点） | native PPM SHA-256 | Poppler PPM SHA-256 | 原图 normalized MAE |
| --- | --- | --- | ---: |
| 0 | `897259f91ef9018de1267b6c3c55844cbc9e02148d95494288cc8618acd29b54` | `d033caa417a46bfba4b6ed93ac53306078bd1849d2a63f6429e654b62c9cfe53` | 0.0600187849 |
| 1 | `842512e5e1dc0d69a3ecda4c5ddfd1c443fdf1badbd1f8412e9ac7fe60f6a299` | `e443566274f97f667652dec1cd291e84fb1be14bad64cac1c23114cf3f244c66` | 0.0686939156 |
| 2 | `c0c47a266523b470305f512f1598ddde300eb2b5790e8c0d8386c213aad4eb63` | `a5fc753d772e0b086bb706ccaa04102f4a44526735d2dd14c95e48b3bbf01ace` | 0.0701649731 |

## 云端图像与审阅范围

| 原页 | 独立诊断 run / job | 诊断源码 | 提供的图像范围 |
| --- | --- | --- | --- |
| 0 | [39891838855 / 120213179284](https://github.com/NoGod3524/EXReader/actions/runs/39891838855/job/120213179284) | `9d021b72697663866f60e509c13a4e545ee4bbf7` | 原分辨率 y=0..520，native/reference/放大差分三栏 |
| 1 | [39892230031 / 120214419645](https://github.com/NoGod3524/EXReader/actions/runs/39892230031/job/120214419645) | `b7c34aeeb003f945a720d41f60d88e232d03ecb7` | 整页 306×396 缩略及原分辨率 y=140..400 文字细节 |
| 2 | [39892230031 / 120214419925](https://github.com/NoGod3524/EXReader/actions/runs/39892230031/job/120214419925) | `b7c34aeeb003f945a720d41f60d88e232d03ecb7` | 同上 |

审阅方式是 Codex 集成代理通过 GitHub 连接读取日志中的有界 PNG，在对话工具内查看；没有把工件下载到用户电脑。
这不是人工操作验收。首次首面 PNG 已在旧失败 job `120212176163` 中完整输出，后续因第二页超图像大小界而失败；
另一次旧失败 job `120212620369` 暴露 Ubuntu Pillow 枚举版本差异。两次失败保留，后继诊断均完成。

在已提供视图中，没有发现整块内容遗漏、全局位置漂移或表格结构缺失；可见差异主要集中在字形边缘、字重与细线覆盖。
这不能证明全部 6–7% MAE 都来自抗锯齿，也不覆盖首面未展示的下部细节或逐字字体语义。
原图差分是后续问题排查和回归审阅的证据，不是正确性得分。

## 新 SDK 与预算出口

新 SDK 必须重新执行全部 12 个参考页和完整测量计划。这些旧图的审阅记录不转授旧 CI 通过状态。
如果新 W9 原始图字节及规范 UTF-8/位置签名完全相同，可以记录为同一图像现象；新源码仍要有自己的执行证据。

正式预算必须从完整、有效且 digest 绑定的 baseline report 取得数值与每 route 的本引擎
RGBA、规范 UTF-8 和位置签名。跨源码签名变化拒绝并要求明确审阅及新基线登记；
Poppler 逐页容差表示已审阅差分的回归边界，始终不授予 render parity。
