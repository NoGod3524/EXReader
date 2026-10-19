# 更新日志

最新版本：**3.33.0**。整理日期：2026-10-19。

## 编号口径

- 超大更新升主版本，中等更新升次版本，小 bug 修复升补丁版本；升前两段时，后续段归零。
- 按功能批次编号，同批实现、测试、构建和验证记录合并记一次版本。纯文档与编号整理归入对应批次。
- 主线共58批：1个初始版本、3次超大更新、41次中等更新、13批小缺陷修复；旧阅读器另有1批独立中等更新。
- 本次回溯覆盖截至 `d3b2e51` 的全部本地及远端跟踪分支：315个不同提交，其中框架主线可达312个（309个第一父提交、3个被合并的开发提交），另有旧阅读器分支3个专有提交。
- 新编号是对历史更新规模的重新归类，日期为相应批次的原提交日期；历史源码中的版本声明、发行附件、提交历史及原验证数据保留原值。下方逐提交索引给出旧声明与新归属。
- 主版本按更新规模分配；SDK二进制兼容性另看ABI epoch。当前为MIT、ABI1、书库schema6，仍在开发中。

## 版本总览

| 新版本 | 原提交日期 | 规模 | 更新 | 主线提交数 |
| --- | --- | --- | --- | --- |
| 0.1.0 | 2026-10-15 | 初始版本 | 本地优先阅读器 | 1 |
| 0.2.0 | 2026-10-15 | 中等更新 | 跨平台原生打包与系统接入 | 15 |
| 0.2.1 | 2026-10-15 | 小缺陷修复 | 阅读视口与预览包修正 | 5 |
| 1.0.0 | 2026-10-15 | 超大更新 | 从阅读器拆出无UI框架 | 5 |
| 2.0.0 | 2026-10-15 | 超大更新 | 将JavaScript底座重写为C11 | 2 |
| 2.1.0 | 2026-10-15–2026-10-16 | 中等更新 | EPUB文档树与基础图文排版 | 2 |
| 2.1.1 | 2026-10-16 | 小缺陷修复 | Windows图像分配与运行库链接 | 1 |
| 2.2.0 | 2026-10-16 | 中等更新 | 开放文档构造、锚点与按需加载 | 3 |
| 2.2.1 | 2026-10-16 | 小缺陷修复 | Windows SDK示例路径 | 1 |
| 2.3.0 | 2026-10-16 | 中等更新 | 字素、字体回退与有界分页 | 5 |
| 2.4.0 | 2026-10-16 | 中等更新 | 原生文字塑形与双向排版 | 1 |
| 2.4.1 | 2026-10-16 | 小缺陷修复 | 文字、锚点与格式解析审计修复 | 13 |
| 2.5.0 | 2026-10-16 | 中等更新 | 完整阅读会话基础 | 7 |
| 2.6.0 | 2026-10-16–2026-10-17 | 中等更新 | FB2、DOCX和RTF结构化解析 | 8 |
| 2.7.0 | 2026-10-17 | 中等更新 | MOBI/KF8与封面导入 | 12 |
| 3.0.0 | 2026-10-17 | 超大更新 | 新增原生PDF、矢量绘制和固定页体系 | 34 |
| 3.1.0 | 2026-10-17 | 中等更新 | 有声书模型与Swift/JNI基础 | 7 |
| 3.2.0 | 2026-10-17 | 中等更新 | RTF表格列表、HTML导出与去重 | 7 |
| 3.3.0 | 2026-10-17 | 中等更新 | EPUB CFI定位 | 5 |
| 3.4.0 | 2026-10-17 | 中等更新 | SDK兼容契约、索引与标注迁移 | 6 |
| 3.5.0 | 2026-10-17 | 中等更新 | PDF元数据与原生标注读取 | 6 |
| 3.6.0 | 2026-10-17 | 中等更新 | PDF标注写回、Unicode断行和PCM输出 | 3 |
| 3.7.0 | 2026-10-17 | 中等更新 | MP3、软连字符与PDF元数据编辑 | 3 |
| 3.8.0 | 2026-10-17 | 中等更新 | 竖排、Type3、AAC/M4B与EPUB编辑 | 2 |
| 3.9.0 | 2026-10-17 | 中等更新 | 混排、可变字体、复杂文字和变速 | 3 |
| 3.9.1 | 2026-10-17 | 小缺陷修复 | Swift仅字形字体接入 | 1 |
| 3.10.0 | 2026-10-17 | 中等更新 | PDF专色函数与音频元数据 | 5 |
| 3.11.0 | 2026-10-17 | 中等更新 | 彩色和位图字体 | 6 |
| 3.12.0 | 2026-10-17 | 中等更新 | DeviceN与多输入采样函数 | 4 |
| 3.13.0 | 2026-10-17 | 中等更新 | CBZ固定页与ICC色彩管理 | 4 |
| 3.14.0 | 2026-10-17 | 中等更新 | CMYK/YCCK JPEG原生采样 | 1 |
| 3.15.0 | 2026-10-17 | 中等更新 | 加密PDF标准认证 | 1 |
| 3.16.0 | 2026-10-17 | 中等更新 | 表格列宽、对齐和边框合并 | 4 |
| 3.17.0 | 2026-10-17–2026-10-18 | 中等更新 | 浮动绕排与跨页续排 | 7 |
| 3.18.0 | 2026-10-18 | 中等更新 | 可选语言词典自动断词 | 8 |
| 3.19.0 | 2026-10-18 | 中等更新 | 可改写断词与源位置映射 | 7 |
| 3.19.1 | 2026-10-18 | 小缺陷修复 | 改写文字的Unicode边界 | 3 |
| 3.19.2 | 2026-10-18 | 小缺陷修复 | 改写文字的双向上下文 | 5 |
| 3.19.3 | 2026-10-18 | 小缺陷修复 | 生成拼写的字素换行 | 2 |
| 3.20.0 | 2026-10-18 | 中等更新 | 断词拼写大小写策略 | 2 |
| 3.20.1 | 2026-10-18 | 小缺陷修复 | 条件复合词词根重建 | 2 |
| 3.21.0 | 2026-10-18 | 中等更新 | 高表格独立续排与内存控制 | 7 |
| 3.22.0 | 2026-10-18 | 中等更新 | RGB混合及隔离/非隔离透明组 | 4 |
| 3.22.1 | 2026-10-18 | 小缺陷修复 | 构建与验证工具维护 | 4 |
| 3.23.0 | 2026-10-18 | 中等更新 | 挖空透明组 | 10 |
| 3.24.0 | 2026-10-18 | 中等更新 | 图形状态软遮罩 | 8 |
| 3.24.1 | 2026-10-18 | 小缺陷修复 | 软遮罩继承状态 | 4 |
| 3.25.0 | 2026-10-18 | 中等更新 | 区域化透明组缓冲 | 7 |
| 3.26.0 | 2026-10-18 | 中等更新 | 渲染意图、CMYK Matte和灰度组 | 5 |
| 3.26.1 | 2026-10-18 | 小缺陷修复 | 未实现渐变的错误分类 | 2 |
| 3.27.0 | 2026-10-18 | 中等更新 | 轴向与径向渐变 | 2 |
| 3.28.0 | 2026-10-19 | 中等更新 | CCITT、网格渐变与虚点边框 | 7 |
| 3.28.1 | 2026-10-19 | 小缺陷修复 | Type 4网格共享边 | 2 |
| 3.29.0 | 2026-10-19 | 中等更新 | 扩展对象流 | 6 |
| 3.30.0 | 2026-10-19 | 中等更新 | 逐边边框与跨页表头 | 7 |
| 3.31.0 | 2026-10-19 | 中等更新 | Coons/Tensor渐变与原生CMYK组 | 7 |
| 3.32.0 | 2026-10-19 | 中等更新 | MIT授权、完整默认ICC与渲染审计 | 5 |
| 3.33.0 | 2026-10-19 | 中等更新 | 稳定核心与可选组件分层 | 3 |

## 各版本变更（从新到旧）

### 3.33.0 — 稳定核心与可选组件分层

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0、0.20.0。

核心、PDF、PDF编辑、音频、书库、索引形成独立CMake目标和版本字段；拆分公开/内部头、安装依赖和组件开关，默认总库保留304个导出，修复裁剪软遮罩预算/内存报告。含验证记录及此前0.20.0元数据调整；本次全历史编号整理仍归入此批。

包含提交：[`716235e`](https://github.com/NoGod3524/EXReader/commit/716235e6ab4c5bb944c2e240b6a173289b3ab725)、[`ba9e13f`](https://github.com/NoGod3524/EXReader/commit/ba9e13fc870ad6f41046ffaccc21ce9a759e7690)、[`d3b2e51`](https://github.com/NoGod3524/EXReader/commit/d3b2e51092920d89fa71f10c623b6588c535c77e)。

### 3.32.0 — MIT授权、完整默认ICC与渲染审计

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0。

原创代码改MIT；压缩内嵌完整默认CMYK ICC，修复渐变透明度/遮罩、网格插值/边缘、组坐标与灰度清理、double边框引用等问题；开始拆内部职责并检查层依赖，修正测试数学库及LittleCMS定点溢出。

包含提交：[`ea38802`](https://github.com/NoGod3524/EXReader/commit/ea38802b3b2e53218b19a55612f885b81edc18f5)、[`2d49f1f`](https://github.com/NoGod3524/EXReader/commit/2d49f1ffbd5544f8ff7dc47c88ad452aee358d08)、[`34a21ca`](https://github.com/NoGod3524/EXReader/commit/34a21ca7c47f07318af0a78fddb356caa2bf01c6)、[`55089af`](https://github.com/NoGod3524/EXReader/commit/55089af988820c1b3ee68b9853f7f4dac907e757)、[`127950e`](https://github.com/NoGod3524/EXReader/commit/127950e7a0592bbc0f100e06d92cea9234c26303)。

### 3.31.0 — Coons/Tensor渐变与原生CMYK组

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0。

加入Type 6/7网格渐变、四分量DeviceCMYK画布缓冲，以及PDF端到端CMYK组接入；保留图像/渐变分色等后续审计项。

包含提交：[`f0fd4b5`](https://github.com/NoGod3524/EXReader/commit/f0fd4b5209bc3108303adfef2ef449ba4552a04f)、[`cbf7804`](https://github.com/NoGod3524/EXReader/commit/cbf7804e2a9807352f910020e79ad9a0ea6cfe8d)、[`a959d79`](https://github.com/NoGod3524/EXReader/commit/a959d79143f537154466d8c0a0230dac90f99e4d)、[`8feb927`](https://github.com/NoGod3524/EXReader/commit/8feb92716eb782dea35a4a25330097fda6db8c66)、[`1d24bf7`](https://github.com/NoGod3524/EXReader/commit/1d24bf79ee36acc2b171d65b46e495e3908d2b86)、[`f9a4491`](https://github.com/NoGod3524/EXReader/commit/f9a4491a966aa0ccfba86f61263582591b37c514)、[`8467141`](https://github.com/NoGod3524/EXReader/commit/846714194b2de8458beb774937c49fff7a183711)。

### 3.30.0 — 逐边边框与跨页表头

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0。

加入CSS double、四边独立宽度/样式/颜色及简写/长写；表格跨页重复thead，补块级/表格绘制测试。border-spacing继续待实现。

包含提交：[`8f3fbc8`](https://github.com/NoGod3524/EXReader/commit/8f3fbc865fd57f026fde691631e4836aac97e73d)、[`bd0dfe7`](https://github.com/NoGod3524/EXReader/commit/bd0dfe737e3b39033919c3c0e3dc6d4e016fb08b)、[`f4cee53`](https://github.com/NoGod3524/EXReader/commit/f4cee53f819f56fb4fa036331267e740c6358c62)、[`444424c`](https://github.com/NoGod3524/EXReader/commit/444424c737bb59c5329e5bbe6885fcb97bfb7a79)、[`aa59693`](https://github.com/NoGod3524/EXReader/commit/aa59693564358e84547443652fc6250aa3c0ff89)、[`2a897d1`](https://github.com/NoGod3524/EXReader/commit/2a897d1637093acb8c4faf167fce4bdebc9a150e)、[`db0ebae`](https://github.com/NoGod3524/EXReader/commit/db0ebae537970a85872ebca4df4cd33075a0ca59)。

### 3.29.0 — 扩展对象流

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0。

支持对象流/Extends链；补审计、默认CMYK差异、ICC打包选项和公开语料基线。

包含提交：[`50c0eeb`](https://github.com/NoGod3524/EXReader/commit/50c0eebcd9985665388ae21f2a47533de2aa282c)、[`04dda84`](https://github.com/NoGod3524/EXReader/commit/04dda8468c4626552375efc4f5f73fd4262469eb)、[`055c125`](https://github.com/NoGod3524/EXReader/commit/055c125d0292235c80f83002567f6b76ee49a0de)、[`0f0f5ab`](https://github.com/NoGod3524/EXReader/commit/0f0f5abdd75604d7e230cd5d09f60c4c98bf082f)、[`c8757d1`](https://github.com/NoGod3524/EXReader/commit/c8757d1a8108c7954f70a1f12b44245da5d11c18)、[`49f30b9`](https://github.com/NoGod3524/EXReader/commit/49f30b925da9182dcf7dfa0d23dc362860e81c53)。

### 3.28.1 — Type 4网格共享边

小缺陷修复；原提交日期：2026-10-19；历史包声明：0.19.0。

修复flag 2时续接三角形选取错误共享边的问题，记录Type 7外部样本阻塞。

包含提交：[`6a8992f`](https://github.com/NoGod3524/EXReader/commit/6a8992faee8f5e5d3babcc666eb490c384477acf)、[`d43bac2`](https://github.com/NoGod3524/EXReader/commit/d43bac21604bbdc5d09123eaeec2a4e409d0a3d3)。

### 3.28.0 — CCITT、网格渐变与虚点边框

中等更新；原提交日期：2026-10-19；历史包声明：0.19.0。

加入CCITT G3/G4、从图像高度推导缺省Rows、Type 4/5网格渐变，以及CSS dashed/dotted边框和相应用例。d715fb9虽以回滚为题，其实际差异新增CCITT并保留前批功能。

包含提交：[`d715fb9`](https://github.com/NoGod3524/EXReader/commit/d715fb9fb741cad03a05518a9f2abaafabb3b574)、[`dbb9d16`](https://github.com/NoGod3524/EXReader/commit/dbb9d160969271adec3e087bba7fe69d560c58f3)、[`cbe4d3d`](https://github.com/NoGod3524/EXReader/commit/cbe4d3d3934cfb1274d77d488e628fbfb653e374)、[`360b081`](https://github.com/NoGod3524/EXReader/commit/360b081d0104670d928021d1443ca9dfb523b933)、[`db70495`](https://github.com/NoGod3524/EXReader/commit/db7049547407a7021504911512f815f7dee7b8e9)、[`47a7ed1`](https://github.com/NoGod3524/EXReader/commit/47a7ed1222fd748b0c2da600c99036d4db6bd8a6)、[`ae811f7`](https://github.com/NoGod3524/EXReader/commit/ae811f796582c1e45274ffe8a82283cfd4bbe6e6)。

### 3.27.0 — 轴向与径向渐变

中等更新；原提交日期：2026-10-18；历史包声明：0.19.0。

将独立实验的PDF Type 2轴向渐变合入主线，并加入Type 3径向渐变。

包含提交：[`cffc2c1`](https://github.com/NoGod3524/EXReader/commit/cffc2c1d39ebc6b9a8ef891575f03b592e4e33b9)、[`139c023`](https://github.com/NoGod3524/EXReader/commit/139c023431a21b694872335d23a5c8726968f677)、[`255bb34`](https://github.com/NoGod3524/EXReader/commit/255bb347acdab783367caea435870c05212e37aa)、[`3db2b83`](https://github.com/NoGod3524/EXReader/commit/3db2b838f593fe5643d34fae180ff3b29e471354)。

### 3.26.1 — 未实现渐变的错误分类

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.19.0。

将尚未实现的sh操作从格式损坏改为明确不支持，并修正回归预期。

包含提交：[`58b2dd0`](https://github.com/NoGod3524/EXReader/commit/58b2dd0773400ed612a886f9a41e833a47aa0bb3)、[`5374ab7`](https://github.com/NoGod3524/EXReader/commit/5374ab78096fedc64d77875046f9729dd14d8aea)。

### 3.26.0 — 渲染意图、CMYK Matte和灰度组

中等更新；原提交日期：2026-10-18；历史包声明：0.19.0。

将PDF及单图rendering intent传给ICC，接入四分量CMYK Matte与DeviceGray组亮度合成；OutputIntent继续单独跟踪。

包含提交：[`4382d04`](https://github.com/NoGod3524/EXReader/commit/4382d041f4046a12165d063965299da925e23f10)、[`a12cba1`](https://github.com/NoGod3524/EXReader/commit/a12cba11087db78bbe7d7924d1a4d438871629f7)、[`58eba2d`](https://github.com/NoGod3524/EXReader/commit/58eba2dde6bb2c9f233a1ec34a69abb096626d85)、[`d66e1be`](https://github.com/NoGod3524/EXReader/commit/d66e1be4e4d9b1847753fe47ee54854a47854dd7)、[`a8015dd`](https://github.com/NoGod3524/EXReader/commit/a8015dd2b4a06e111c7ddd2eb368047a998c483d)。

### 3.25.0 — 区域化透明组缓冲

中等更新；原提交日期：2026-10-18；历史包声明：0.19.0。

将工作缓冲引入独立原点并按透明组区域分配，减少全页中间缓冲；修复设备范围报告和组初始化，补隔离组及区域验收。

包含提交：[`a3b7d2e`](https://github.com/NoGod3524/EXReader/commit/a3b7d2eefbaa9aa3b98be58b3f054065321455fa)、[`e6ffe8b`](https://github.com/NoGod3524/EXReader/commit/e6ffe8b5e7010d1784bb170660cf3e2bdbce1899)、[`212c8e5`](https://github.com/NoGod3524/EXReader/commit/212c8e5c485c171ad45b85ffcf3f2aca0349b974)、[`8a415a8`](https://github.com/NoGod3524/EXReader/commit/8a415a8b10e9ff93fc51c9d48f26193cfd2b9fa0)、[`a9fbcc8`](https://github.com/NoGod3524/EXReader/commit/a9fbcc882d468bbc1629618cf1256893f9e5714a)、[`ad5b732`](https://github.com/NoGod3524/EXReader/commit/ad5b732131acbae69afc09c54ecb3020fe1b1d3d)、[`5d94daa`](https://github.com/NoGod3524/EXReader/commit/5d94daa302fd8fa0351adb9c890b2cdcaa00c386)、[`9fa6c4c`](https://github.com/NoGod3524/EXReader/commit/9fa6c4c9781528526cb0b81f4bcec4e03066db45)。

### 3.24.1 — 软遮罩继承状态

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.19.0。

修复软遮罩作为绘制状态继承的语义；补公开PDF语料获取、宿主字体比较和兼容缺口记录。

包含提交：[`85b4797`](https://github.com/NoGod3524/EXReader/commit/85b479716599374f426d46742f63286398718708)、[`993dbd3`](https://github.com/NoGod3524/EXReader/commit/993dbd301c8e12fad17b9d7e094f69f75192e94a)、[`c6d6aaa`](https://github.com/NoGod3524/EXReader/commit/c6d6aaa054ebe060f4db46b95666b2ddd7364f24)、[`9227280`](https://github.com/NoGod3524/EXReader/commit/9227280e7455e64cfea8a37028f908fc1956179e)。

### 3.24.0 — 图形状态软遮罩

中等更新；原提交日期：2026-10-18；历史包声明：0.19.0。

接入画布/sink的Alpha/Luminosity软遮罩、指数transfer函数、q/Q、组语义/色彩空间/嵌套和拒绝用例；加入MuPDF对照工具。

包含提交：[`3a178bf`](https://github.com/NoGod3524/EXReader/commit/3a178bfe22fc2414ccca388e554cc6d80734d108)、[`e2d86b3`](https://github.com/NoGod3524/EXReader/commit/e2d86b3ace0eeaad13c1df4ff24d403b304528b0)、[`0b08537`](https://github.com/NoGod3524/EXReader/commit/0b08537939ecf42a9fcfa37987cc2e7243987956)、[`4924d8c`](https://github.com/NoGod3524/EXReader/commit/4924d8c8f84e95132630f99548f9a98020aa1ebe)、[`c3504ab`](https://github.com/NoGod3524/EXReader/commit/c3504abc91a64655cd0efc88c1f8b33378f01ba4)、[`bf1a646`](https://github.com/NoGod3524/EXReader/commit/bf1a64689d44852fefae8f5d3e648409724a4078)、[`685961d`](https://github.com/NoGod3524/EXReader/commit/685961da63618ad1f93c951521d2d4878e9f75e4)、[`12fd6f9`](https://github.com/NoGod3524/EXReader/commit/12fd6f902d2f983ae15370bfc396f39a983fea81)。

### 3.23.0 — 挖空透明组

中等更新；原提交日期：2026-10-18；历史包声明：0.19.0。

实现画布/PDF knockout及嵌套组初始背景语义；建立独立Decimal参考、42场景、预算/取消/旧宿主回归与完整验收矩阵。

包含提交：[`e8b5b7c`](https://github.com/NoGod3524/EXReader/commit/e8b5b7cf1be5618e899aec9c58713d54225f38cf)、[`6ced661`](https://github.com/NoGod3524/EXReader/commit/6ced661c2e15266d51ef4f8728a917c620d51ee9)、[`79c8d41`](https://github.com/NoGod3524/EXReader/commit/79c8d4180ff83bff0aef54840d73ddd065081637)、[`ac99751`](https://github.com/NoGod3524/EXReader/commit/ac997517bb9cab59ad4ddac2abc30ef92d26cff2)、[`ceabedd`](https://github.com/NoGod3524/EXReader/commit/ceabedd23b81eb361ffda907ac8c8698835c275f)、[`e057699`](https://github.com/NoGod3524/EXReader/commit/e0576992a587b0c718689e9fe9c844f527f2fef0)、[`060b7e0`](https://github.com/NoGod3524/EXReader/commit/060b7e05d1eda2adf5c1d0ca5cac7eb4f51d92a0)、[`348d52b`](https://github.com/NoGod3524/EXReader/commit/348d52bb6c3545f1d214f2b4af79e1586c9a59ef)、[`4da2746`](https://github.com/NoGod3524/EXReader/commit/4da27468522dda97f61401b113270b048d6906f6)、[`e37de3f`](https://github.com/NoGod3524/EXReader/commit/e37de3f63fa815fc0f73f56d71aab2e98d3df46c)。

### 3.22.1 — 构建与验证工具维护

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.19.0。

整理版本/支持矩阵，增加解析器fuzz驱动；修复fuzz作业构建范围，记录七项CI结果。

包含提交：[`c58fce5`](https://github.com/NoGod3524/EXReader/commit/c58fce51f4a1bb2ada12dccd75d927543a40124a)、[`c31311d`](https://github.com/NoGod3524/EXReader/commit/c31311d63d0f67585c9a16cf9e3eeda9d8ad9b4a)、[`2228f59`](https://github.com/NoGod3524/EXReader/commit/2228f591aafaa72ce4ca9d4c24f54496f2aaa432)、[`bbb18a7`](https://github.com/NoGod3524/EXReader/commit/bbb18a7f81ac5583b25af1018b0d2770a7377536)。

### 3.22.0 — RGB混合及隔离/非隔离透明组

中等更新；原提交日期：2026-10-18；历史包声明：0.18.0。

新增16种RGB混合模式、隔离Form/AP/页面组、嵌套图层和大小标记sink；接入非隔离组的背景移除与高精度alpha，并验证预算/取消/旧接口。

包含提交：[`a1411af`](https://github.com/NoGod3524/EXReader/commit/a1411afc9547c61950ecb424049a8f7be43b0d11)、[`2fe46c6`](https://github.com/NoGod3524/EXReader/commit/2fe46c6c288c3691ca0bf4caedaac90f87300b68)、[`ec8d4a9`](https://github.com/NoGod3524/EXReader/commit/ec8d4a98cdd6e63fa10a67e9a8521dfac743dd3e)、[`381f5e7`](https://github.com/NoGod3524/EXReader/commit/381f5e7527ccecd31842de258fcf5c8337d8f0c5)。

### 3.21.0 — 高表格独立续排与内存控制

中等更新；原提交日期：2026-10-18；历史包声明：0.18.0。

新增高行/跨行组的单元格独立游标和试排提交；避免保留整格字形以测量高度，减少OpenType无用分类，补平台字体、SDK和性能验证。

包含提交：[`840efcf`](https://github.com/NoGod3524/EXReader/commit/840efcfdcca2f7070453696a3e9c61a3580c3f5c)、[`fb3f76b`](https://github.com/NoGod3524/EXReader/commit/fb3f76b13a95486994ab2198a59136294582bcc5)、[`4c78920`](https://github.com/NoGod3524/EXReader/commit/4c789208c3acb20e4fb5eb6ce97f75351474e8f0)、[`4a994c0`](https://github.com/NoGod3524/EXReader/commit/4a994c040e26541a34df84f682d806b35a8798fe)、[`ef286bf`](https://github.com/NoGod3524/EXReader/commit/ef286bf31e3e05b51135bd65fbd0a86f37bf8f94)、[`b644e95`](https://github.com/NoGod3524/EXReader/commit/b644e95e89b54c0ee159fce0157f3b1cb469cc6b)、[`79236e8`](https://github.com/NoGod3524/EXReader/commit/79236e84f8b80ec08dd656e1fd616e18bc52b111)。

### 3.20.1 — 条件复合词词根重建

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.18.0。

修复条件词根重建及源区间映射，保持Unicode、大小写和有界工作队列约束。

包含提交：[`177b6e1`](https://github.com/NoGod3524/EXReader/commit/177b6e1d6b7587612cde08340006bd2cd4adf21e)、[`61e584a`](https://github.com/NoGod3524/EXReader/commit/61e584ae8bd7c13be97bb8a5459c185361899dbc)。

### 3.20.0 — 断词拼写大小写策略

中等更新；原提交日期：2026-10-18；历史包声明：0.18.0。

新增WORD/LITERAL策略、Unicode完整大小写映射及tr/az/lt上下文、标题首字保留与宿主接入验证。

包含提交：[`f9754b0`](https://github.com/NoGod3524/EXReader/commit/f9754b05032f1b970d5ad75c111b91b7aadffab1)、[`5f7a4ba`](https://github.com/NoGod3524/EXReader/commit/5f7a4ba32b581af5ac96cdeaa7173d2ca164d730)。

### 3.19.3 — 生成拼写的字素换行

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.18.0。

按显示字素切分生成文字，修复跨页及重复源偏移上的继续换行。

包含提交：[`365f691`](https://github.com/NoGod3524/EXReader/commit/365f6916d32ee9c7c570e52124c48f36deea90b0)、[`a08a7cd`](https://github.com/NoGod3524/EXReader/commit/a08a7cd0cd372dd402bc08f99630202e0a54eefd)。

### 3.19.2 — 改写文字的双向上下文

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.18.0。

修复显示串双向与AUTO方向、ruby快速判断和未来文字上下文稳定性，防止发布后分页方向变化。

包含提交：[`4421413`](https://github.com/NoGod3524/EXReader/commit/4421413c8a4986cd43b0821dd64be4897007f011)、[`3e332a6`](https://github.com/NoGod3524/EXReader/commit/3e332a6096666f3a7a96d4961a2e73a932876581)、[`93a4f27`](https://github.com/NoGod3524/EXReader/commit/93a4f271e315c627a3cf7be79b802fb648c2c703)、[`dde7671`](https://github.com/NoGod3524/EXReader/commit/dde7671327a29ce14484ab84e897b2a2821266ea)、[`fb4e13c`](https://github.com/NoGod3524/EXReader/commit/fb4e13c753bdea12583cea75703688c5d0db1bb0)。

### 3.19.1 — 改写文字的Unicode边界

小缺陷修复；原提交日期：2026-10-18；历史包声明：0.18.0。

重放替换后的显示字素/换行状态，避免空carry塑形中的零长度复制。

包含提交：[`ddeae97`](https://github.com/NoGod3524/EXReader/commit/ddeae9735ee33266e0144b2a6496d8f1d19aa8af)、[`fecef3c`](https://github.com/NoGod3524/EXReader/commit/fecef3c642112a4ed50d5841429578e77e0e6ef9)、[`072d131`](https://github.com/NoGod3524/EXReader/commit/072d1313a8d87b5458613b6b2a8b66a7ac5c9775)。

### 3.19.0 — 可改写断词与源位置映射

中等更新；原提交日期：2026-10-18；历史包声明：0.18.0。

新增拥有式discretionary查询和provider，拼写替换进入测量/塑形/分页；修复零切分插入的源进度，支持改写余词重匹配与位置映射。

包含提交：[`8067ede`](https://github.com/NoGod3524/EXReader/commit/8067ede251d9a3298c07e33f33b5e59e4aaaed3f)、[`5b1aa4b`](https://github.com/NoGod3524/EXReader/commit/5b1aa4b35f2cc75c5a1402a25736eb94d78f55ff)、[`fd95ac4`](https://github.com/NoGod3524/EXReader/commit/fd95ac43ab0585ea4fead7f48c9dd2c39c77f1a6)、[`4ee3923`](https://github.com/NoGod3524/EXReader/commit/4ee39235cf49e723b2f6a975cf3948873c430dcf)、[`66b71a8`](https://github.com/NoGod3524/EXReader/commit/66b71a87296662e723b6332b7681ed30f1199380)、[`f27ace2`](https://github.com/NoGod3524/EXReader/commit/f27ace2ca341c26dd94de055a068013651182e1e)、[`d3c4d75`](https://github.com/NoGod3524/EXReader/commit/d3c4d75afd120e6d6b99e7576e1d912e5876cc78)。

### 3.18.0 — 可选语言词典自动断词

中等更新；原提交日期：2026-10-18；历史包声明：0.18.0。

新增语言模式词典和安全provider，接入实际排版；补Unicode 17 NFC与原文字节映射、复合词递归和规则，并验证跨平台结果。

包含提交：[`e9e3b64`](https://github.com/NoGod3524/EXReader/commit/e9e3b64d5cfa578d9ab224302fc5c12666a4da94)、[`6d14acf`](https://github.com/NoGod3524/EXReader/commit/6d14acf5586c38977bc948dab8d0fff3d212b04b)、[`daa7cc5`](https://github.com/NoGod3524/EXReader/commit/daa7cc570d6bc4edc49490b3b0c2035b06b70069)、[`ac0a003`](https://github.com/NoGod3524/EXReader/commit/ac0a0032caca58d45506a6be43323ab143c1cf29)、[`1eb9f0d`](https://github.com/NoGod3524/EXReader/commit/1eb9f0ddef27f5a5c7c7ffd777132eaacc1f1352)、[`249f756`](https://github.com/NoGod3524/EXReader/commit/249f756f233340826e6f7add5c21b650f662a24e)、[`5037678`](https://github.com/NoGod3524/EXReader/commit/5037678dec997515814af6e61beb6c6984b8496d)、[`418c33d`](https://github.com/NoGod3524/EXReader/commit/418c33d8ab233888e3cdbe0684bf5b534871dd6b)。

### 3.17.0 — 浮动绕排与跨页续排

中等更新；原提交日期：2026-10-17 / 2026-10-18；历史包声明：0.18.0。

接入float/clear、逐行可用通道、稳定源位置、嵌套深度限制、长浮动分页游标/检查点，以及普通表格BFC与浮动并排；补性能与跨平台验证。

包含提交：[`7abacb9`](https://github.com/NoGod3524/EXReader/commit/7abacb9d45e4dc3bd4a5377eefe149243d176ef2)、[`98e4250`](https://github.com/NoGod3524/EXReader/commit/98e4250702e43f1d6b256ce7da26ac5ebbc4b876)、[`a94ca62`](https://github.com/NoGod3524/EXReader/commit/a94ca62d3739a7f6c5317f49772c52c0ab7c428c)、[`9ec2349`](https://github.com/NoGod3524/EXReader/commit/9ec2349c51c6030a39b6497ebff652494bd12e3f)、[`2849fa6`](https://github.com/NoGod3524/EXReader/commit/2849fa67963f56b9bdcb077d36eb9c0697fd9ca1)、[`5fe3ca9`](https://github.com/NoGod3524/EXReader/commit/5fe3ca90c1167d497300e57ff333c00c2c308ab1)、[`4c9c19f`](https://github.com/NoGod3524/EXReader/commit/4c9c19f7ed2fb9e1b2d7a7692c2ecc92d412d5eb)。

### 3.16.0 — 表格列宽、对齐和边框合并

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

实现指定列宽、原生塑形驱动的intrinsic列宽、baseline/top/middle/bottom对齐、border-collapse与半宽几何，保持分页检查点坐标一致。

包含提交：[`d4d8fb3`](https://github.com/NoGod3524/EXReader/commit/d4d8fb3e2e14f43f7544bea1caf06839eb5c8883)、[`a99f125`](https://github.com/NoGod3524/EXReader/commit/a99f1254252cbdef1af94f652530d54dbefb72bf)、[`a0117c7`](https://github.com/NoGod3524/EXReader/commit/a0117c741d5fe7dc2c3270dc5480cf9a15cc8c5c)、[`57c9f17`](https://github.com/NoGod3524/EXReader/commit/57c9f17fb07adc4d71087c788a3cf30cadc6823f)。

### 3.15.0 — 加密PDF标准认证

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入Standard R2–R6密码读取、可重试认证与安全状态查询；密码学后端可选。

包含提交：[`65c32d9`](https://github.com/NoGod3524/EXReader/commit/65c32d9f4bda5e7ab4e390a455f480d266cb2785)。

### 3.14.0 — CMYK/YCCK JPEG原生采样

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

在PDF图像解码和色彩转换链中保留CMYK/YCCK JPEG原始采样。

包含提交：[`aa3a329`](https://github.com/NoGod3524/EXReader/commit/aa3a32902335fb15ea8f0e0803900ace98ba0c77)。

### 3.13.0 — CBZ固定页与ICC色彩管理

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入CBZ按需固定页和书库接入，以及有界ICCBased色彩转换；隐藏静态嵌入ICC库的内部符号并完成验证。

包含提交：[`e7ce3ce`](https://github.com/NoGod3524/EXReader/commit/e7ce3ce9c9155c19f957c0fc8d3d7ceb3cbded52)、[`06893f3`](https://github.com/NoGod3524/EXReader/commit/06893f3d6d87d7770590d095659bdb4f6fca917b)、[`a4e70f6`](https://github.com/NoGod3524/EXReader/commit/a4e70f6a6a97e0fa5d8f3e0c992f7ba970440f75)、[`166e5ad`](https://github.com/NoGod3524/EXReader/commit/166e5ad7ebb897d5ff01e7e4d69f645d107caf25)。

### 3.12.0 — DeviceN与多输入采样函数

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

补PDF registration All语义、32输入Type 4、DeviceN、多维及三次采样函数，并记录跨平台色彩/字体验证。

包含提交：[`7e2b55c`](https://github.com/NoGod3524/EXReader/commit/7e2b55c9681aefb0ea27d2a15db4593da5945110)、[`f3727ea`](https://github.com/NoGod3524/EXReader/commit/f3727ea2dab3a15790e377f6e9fd6110d812e5b7)、[`6731b1b`](https://github.com/NoGod3524/EXReader/commit/6731b1ba904402f529023ad516ebf5c1c11efd77)、[`3ea8bca`](https://github.com/NoGod3524/EXReader/commit/3ea8bca3618bed4f4718c445f8317351e27f9601)。

### 3.11.0 — 彩色和位图字体

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入COLR v0图层、sbix与CBDT/CBLC位图字体、emoji不可见组件及Unicode变体序列/回退；修复嵌入式sbix统一打开路径。

包含提交：[`f07af93`](https://github.com/NoGod3524/EXReader/commit/f07af935e3398a6e66b17f3c40c2881905c02426)、[`77bfa02`](https://github.com/NoGod3524/EXReader/commit/77bfa022cc6eb9baa2536ffe67853c6e5f765863)、[`126b1e0`](https://github.com/NoGod3524/EXReader/commit/126b1e0332ce24cbee0d046b7d5879e5cd74beb0)、[`3f8547d`](https://github.com/NoGod3524/EXReader/commit/3f8547d80fdde61a804a631786dd25a6d1c951fd)、[`504e463`](https://github.com/NoGod3524/EXReader/commit/504e463341cc2709731c8b7be8feb23a5b919519)、[`9f52053`](https://github.com/NoGod3524/EXReader/commit/9f520533787e0e5371f4d6679c947103f5b911e7)。

### 3.10.0 — PDF专色函数与音频元数据

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入Separation、指数/拼接/线性采样/Type 4计算器函数；读取QuickTime引用章节、mdta及freeform文字元数据。

包含提交：[`c59d1b8`](https://github.com/NoGod3524/EXReader/commit/c59d1b850bae8ee652e578f5a5771863aee43ec7)、[`fa2942f`](https://github.com/NoGod3524/EXReader/commit/fa2942fdfaa24d3dda136f7da5f89f142723bf9c)、[`847de68`](https://github.com/NoGod3524/EXReader/commit/847de68ee9a6e378765c6d2c094e614be62170b7)、[`98ab5f2`](https://github.com/NoGod3524/EXReader/commit/98ab5f26145b1cc64eaf4df219f75a7466aedc0b)、[`58e907f`](https://github.com/NoGod3524/EXReader/commit/58e907f0df4919b16cf0803b244c77666f48e7fd)。

### 3.9.1 — Swift仅字形字体接入

小缺陷修复；原提交日期：2026-10-17；历史包声明：0.18.0。

修复Swift重排适配器遗漏的glyph-only字体支持。

包含提交：[`43ef9ac`](https://github.com/NoGod3524/EXReader/commit/43ef9ac2f168c5a3fcc09d3641fad38d537721ad)。

### 3.9.0 — 混排、可变字体、复杂文字和变速

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

增加横竖混排续排、可变字体轴/变化定位、WSOLA保音高变速、PDF内联图片、Devanagari/ruby、校准色彩和移动重排API；M4B元数据/封面/章节可不启用AAC读取。

包含提交：[`0f45262`](https://github.com/NoGod3524/EXReader/commit/0f45262b6e6531720c23953f80acaa7fb08e4c0c)、[`55fb274`](https://github.com/NoGod3524/EXReader/commit/55fb27456162517eaf22bcf0b629722e2546cf2c)、[`7ea57fc`](https://github.com/NoGod3524/EXReader/commit/7ea57fcd1522b83b7a46a48840b6428b3ca55ede)。

### 3.8.0 — 竖排、Type3、AAC/M4B与EPUB编辑

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入统一页面竖排、PDF Type3字体、可选AAC/M4A/M4B，以及EPUB原书元数据/封面写回；修正XML测试终止符及BMFF表行初始化。

包含提交：[`a1a1e4d`](https://github.com/NoGod3524/EXReader/commit/a1a1e4d2318c493e70fa5f9226f1654f405b084a)、[`5e82ba3`](https://github.com/NoGod3524/EXReader/commit/5e82ba3114025e4bed2ef6e160b2a7f8ae94c516)。

### 3.7.0 — MP3、软连字符与PDF元数据编辑

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

加入可选无缝MP3、可见软连字符、Info/XMP写回和Swift/JNI PCM接入；修正相关测试头文件与数学库链接。

包含提交：[`888fc49`](https://github.com/NoGod3524/EXReader/commit/888fc491adce0974f179bd1f7ad3d9665a1ce7a3)、[`3b1a905`](https://github.com/NoGod3524/EXReader/commit/3b1a9050c852d07b2b2f1e0e92c31a776053bad5)、[`4b3d166`](https://github.com/NoGod3524/EXReader/commit/4b3d16640411cbd1ead93e3114612af2b9c4ccd8)。

### 3.6.0 — PDF标注写回、Unicode断行和PCM输出

中等更新；原提交日期：2026-10-17；历史包声明：0.18.0。

增加PDF Text/Highlight及线型标注的增量写回、删除和外观绘制；补Unicode 17默认断行、原生FLAC、开放PCM及六平台音频输出适配。增量删除不等同安全擦除。

包含提交：[`5ff51c3`](https://github.com/NoGod3524/EXReader/commit/5ff51c3b0fbe02fe0fade0940c748658e06f3369)、[`590385d`](https://github.com/NoGod3524/EXReader/commit/590385d03a9cf7ad07fe9ef33a39c38b1dd38712)、[`3b27c84`](https://github.com/NoGod3524/EXReader/commit/3b27c84744bb082b09a673e9c417d5bd71c49f3b)。

### 3.5.0 — PDF元数据与原生标注读取

中等更新；原提交日期：2026-10-17；历史包声明：0.97.0、0.98.0、0.99.0、0.100.0、0.18.0。

提供通用Info/XMP元数据读取、Swift/Java所有权封装与原生页标注快照；修正Swift验证变量冲突。首次旧编号归并作为元数据整理随本批记录。

包含提交：[`07d952f`](https://github.com/NoGod3524/EXReader/commit/07d952ff5518f03f9707120dbfad27444ebf26d5)、[`520db83`](https://github.com/NoGod3524/EXReader/commit/520db835dc0b79c6d9729dc7b602fed811978ecd)、[`9c7f186`](https://github.com/NoGod3524/EXReader/commit/9c7f1865f66a559ad0d68ef19d0cf3dad38a993c)、[`5e0d2d9`](https://github.com/NoGod3524/EXReader/commit/5e0d2d941690781d514db462c62b02213244a1b3)、[`6ed05b0`](https://github.com/NoGod3524/EXReader/commit/6ed05b09b08fa260fdb4dc7d4a9e05a3a8b324be)、[`5a756d6`](https://github.com/NoGod3524/EXReader/commit/5a756d6d54c92c134192c40c8951cdc52c684726)。

### 3.4.0 — SDK兼容契约、索引与标注迁移

中等更新；原提交日期：2026-10-17；历史包声明：0.91.0、0.92.0、0.93.0、0.94.0、0.95.0、0.96.0。

引入ABI epoch 1及可搬迁CMake安装包；增加可选持久化全文索引、流式原子重建、稳定阅读位置、原书更新后的进度/标注重投影和Web Annotation交换。

包含提交：[`7dc8d8a`](https://github.com/NoGod3524/EXReader/commit/7dc8d8a9a136cc3258a7348f151e13ff32f7e3f1)、[`891f818`](https://github.com/NoGod3524/EXReader/commit/891f8187ebf2b13d934ef3b0ae7794055637015e)、[`1d30b03`](https://github.com/NoGod3524/EXReader/commit/1d30b03d077300c2e1e12885bfaf9ecedfdb09bf)、[`695d092`](https://github.com/NoGod3524/EXReader/commit/695d0921c2fa2cee082a959365658464329443ff)、[`a0a50a1`](https://github.com/NoGod3524/EXReader/commit/a0a50a1bd42f19ccc8ca1864aaffff4b1576071a)、[`17a826d`](https://github.com/NoGod3524/EXReader/commit/17a826d91552ae93bfdc94e4505e831159c78071)。

### 3.3.0 — EPUB CFI定位

中等更新；原提交日期：2026-10-17；历史包声明：0.86.0、0.87.0、0.88.0、0.89.0、0.90.0。

实现DOM路径、原始spine地址、按目标章加载、点/范围CFI，以及文本断言与唯一上下文恢复。

包含提交：[`5db01d0`](https://github.com/NoGod3524/EXReader/commit/5db01d08e766dcbaf2a328dfe45bd36c42cce172)、[`27746e4`](https://github.com/NoGod3524/EXReader/commit/27746e4892bd8976d0ce67ff7585a4f102dda1b7)、[`2135309`](https://github.com/NoGod3524/EXReader/commit/2135309aa4394247036145eb2393aac60ae328a9)、[`ab8550e`](https://github.com/NoGod3524/EXReader/commit/ab8550e6b1826672637141babd379d84e9ec6204)、[`fb49403`](https://github.com/NoGod3524/EXReader/commit/fb4940304edbe34b55bf657e41a1fa92a5e43405)。

### 3.2.0 — RTF表格列表、HTML导出与去重

中等更新；原提交日期：2026-10-17；历史包声明：0.79.0、0.80.0、0.81.0、0.82.0、0.83.0、0.84.0、0.85.0。

保留RTF行列/合并格/脚注/列表及自动编号；增加HTML目录包资源导出和原子原书去重导入。

包含提交：[`c0c9808`](https://github.com/NoGod3524/EXReader/commit/c0c980815047ddd0c95e1adae0bcc2aa44b88639)、[`adfd228`](https://github.com/NoGod3524/EXReader/commit/adfd228bdc3734b7bc84d92d89d32b3539a306c0)、[`fd411e4`](https://github.com/NoGod3524/EXReader/commit/fd411e442e11046e84eebc941f7d75588303a24b)、[`0c311d8`](https://github.com/NoGod3524/EXReader/commit/0c311d8d7fbfc233274f399e8acad47fbe2b51e6)、[`4973ea6`](https://github.com/NoGod3524/EXReader/commit/4973ea61d42aa275e0da5f55bde6fbfbd3e8b750)、[`8292325`](https://github.com/NoGod3524/EXReader/commit/82923253baef96a972e14e4f6c77d06036981604)、[`713c2a8`](https://github.com/NoGod3524/EXReader/commit/713c2a8b777bbaafcbac91b141dacbe87536e1e5)。

### 3.1.0 — 有声书模型与Swift/JNI基础

中等更新；原提交日期：2026-10-17；历史包声明：0.72.0、0.73.0、0.74.0、0.75.0、0.76.0、0.77.0、0.78.0。

加入开放音频时间线、章节与文本同步、宿主播放控制、WAVE随机读取、续播与时间书签；提供Swift C模块和可选JNI的PDF/字体/PCM适配及安装示例。

包含提交：[`b6b31d7`](https://github.com/NoGod3524/EXReader/commit/b6b31d7561fe88df96ede087d35294f8a8775746)、[`de65c24`](https://github.com/NoGod3524/EXReader/commit/de65c245923db0a6a284855ab3dedc061d4199f9)、[`a0ddece`](https://github.com/NoGod3524/EXReader/commit/a0ddecefec342b802c30dcb4f0351c6b8def958e)、[`c8f07c3`](https://github.com/NoGod3524/EXReader/commit/c8f07c33192b32d88d7da5996cc02a1f78e0d4f1)、[`333f2e2`](https://github.com/NoGod3524/EXReader/commit/333f2e2776a1f5beb7777083792fb7895ee55243)、[`f5e92f1`](https://github.com/NoGod3524/EXReader/commit/f5e92f12d39e778c08c977abfa729081351ec9a3)、[`2aa97a9`](https://github.com/NoGod3524/EXReader/commit/2aa97a96dffcc2792439794994158b41f7eb7fea)。

### 3.0.0 — 新增原生PDF、矢量绘制和固定页体系

超大更新；原提交日期：2026-10-17；历史包声明：0.38.0、0.39.0、0.40.0、0.41.0、0.42.0、0.43.0、0.44.0、0.45.0、0.46.0、0.47.0、0.48.0、0.49.0、0.50.0、0.51.0、0.52.0、0.53.0、0.54.0、0.55.0、0.56.0、0.57.0、0.58.0、0.59.0、0.60.0、0.61.0、0.62.0、0.63.0、0.64.0、0.65.0、0.66.0、0.67.0、0.68.0、0.69.0、0.70.0、0.71.0。

从定位绘制模型开始构建PDF对象/xref/过滤器/字体/内容解释、原生路径与字形栅格、图片与遮罩、通用画布和流式绘制接口；建立按需固定页模型、视口坐标映射、文本搜索/命中/选择、稳定固定页锚点和PDF书库进度。新增完整的一套固定版面处理链路，PDF深度兼容仍按支持矩阵推进。

包含提交：[`12f12cf`](https://github.com/NoGod3524/EXReader/commit/12f12cf20c10414d3a2463a5da6ab5726f342977)、[`3301cf3`](https://github.com/NoGod3524/EXReader/commit/3301cf359168b6e184260df9d7ca89727845719c)、[`2ac097a`](https://github.com/NoGod3524/EXReader/commit/2ac097ae53e18241254432fb3ac26ed29ee6f0d9)、[`6018c88`](https://github.com/NoGod3524/EXReader/commit/6018c881493fb3b233d6765734327fe379e74b9f)、[`605a50f`](https://github.com/NoGod3524/EXReader/commit/605a50fdaa8c69f1880a59153f3268c0f1583e38)、[`aaebfa0`](https://github.com/NoGod3524/EXReader/commit/aaebfa01fc73d5624edcb4a187b63ac0a8a9e2b7)、[`03778cc`](https://github.com/NoGod3524/EXReader/commit/03778cc65adefb79c9f0dc345e79618d65cc1582)、[`477d357`](https://github.com/NoGod3524/EXReader/commit/477d35758f12c03465324a8c2cadc96869107b1c)、[`3255a25`](https://github.com/NoGod3524/EXReader/commit/3255a25535e2e1088429509ceb47da430c437335)、[`325a7f0`](https://github.com/NoGod3524/EXReader/commit/325a7f0a4764eaf651133f7c466aec9635b52500)、[`9a35ebb`](https://github.com/NoGod3524/EXReader/commit/9a35ebb44f75e87f90516b639a53b701d81b4b25)、[`47c50b9`](https://github.com/NoGod3524/EXReader/commit/47c50b9e2679cc57d92ce41ef53fd3f6a554bee4)、[`cf835bb`](https://github.com/NoGod3524/EXReader/commit/cf835bb001a09a3329fd8f600454bd7dfe12829b)、[`2a72314`](https://github.com/NoGod3524/EXReader/commit/2a72314c44e7bce1217329f9d28c37f97e217132)、[`ff33a4b`](https://github.com/NoGod3524/EXReader/commit/ff33a4b6384b30c2cd69334d9056071f0c7922ec)、[`4b20178`](https://github.com/NoGod3524/EXReader/commit/4b201785c42116b809acc9a3f29c7bbd06269da1)、[`ba0b13f`](https://github.com/NoGod3524/EXReader/commit/ba0b13fc413f0a6c4626476f51208cc0d3d4c6fe)、[`79c8cd3`](https://github.com/NoGod3524/EXReader/commit/79c8cd3a3c53029f6a1034588090759df678c0a7)、[`e84c996`](https://github.com/NoGod3524/EXReader/commit/e84c996a81cb7cb025601e6e41b67320b02e7d1f)、[`d3435f9`](https://github.com/NoGod3524/EXReader/commit/d3435f99022fcb935321b5d60485ad762dab8c5c)、[`b536469`](https://github.com/NoGod3524/EXReader/commit/b536469560e2a8a2a3c1cdd4c1bff99dcb0dde33)、[`99ee06d`](https://github.com/NoGod3524/EXReader/commit/99ee06d95f298b97072d64a2634c5c2c2a237d1e)、[`154a2d9`](https://github.com/NoGod3524/EXReader/commit/154a2d9acd873469086a894dbdac93a460b20b06)、[`dd68de3`](https://github.com/NoGod3524/EXReader/commit/dd68de3e94b753caadff2ed9212e5c141bf39262)、[`f080abd`](https://github.com/NoGod3524/EXReader/commit/f080abd20cfaac246bae338fe342b383bc702cea)、[`dcb66ab`](https://github.com/NoGod3524/EXReader/commit/dcb66abf5291fb2da5b04b04dd58264f9c5d4089)、[`8031631`](https://github.com/NoGod3524/EXReader/commit/8031631d3260aba27b6ef20caf0dacb678e5f2af)、[`ed66563`](https://github.com/NoGod3524/EXReader/commit/ed66563635c1ebdcdd810df44571cfb5132ad104)、[`b167c58`](https://github.com/NoGod3524/EXReader/commit/b167c588907371e3a4c9ca19389c17d7ce6f4197)、[`06bcf9f`](https://github.com/NoGod3524/EXReader/commit/06bcf9fd4d58da41a99fc9f1481696c58960fc4d)、[`4c5980b`](https://github.com/NoGod3524/EXReader/commit/4c5980bda82a8ae7bbf7a830c34510faa3496a6e)、[`dacd144`](https://github.com/NoGod3524/EXReader/commit/dacd14479e3c86eba693d851ebd327df22d1598a)、[`934dd91`](https://github.com/NoGod3524/EXReader/commit/934dd9108b771c6566d13621442d25e498d9c98f)、[`792076e`](https://github.com/NoGod3524/EXReader/commit/792076e0b500fbfb952ffd2e30eb054e60ff3b8e)。

### 2.7.0 — MOBI/KF8与封面导入

中等更新；原提交日期：2026-10-17；历史包声明：0.27.0、0.28.0、0.29.0、0.30.0、0.31.0、0.32.0、0.33.0、0.34.0、0.35.0、0.36.0、0.37.0。

加入HUFF/CDIC、KF8骨架与片段重建、CSS/字体/图片、片段定位、NCX/guide导航、混合版本选择、命名空间和ORDT；保留原书标题/封面并原子导入书库，修正二进制CSS测试终止符。

包含提交：[`7566f61`](https://github.com/NoGod3524/EXReader/commit/7566f619b05a87982f49d7655bcc154430da1d36)、[`bcce6f0`](https://github.com/NoGod3524/EXReader/commit/bcce6f0d26372a80621adeabd56732f3d5a95176)、[`171120c`](https://github.com/NoGod3524/EXReader/commit/171120c8a0357d8fb4e65781907d7c98bf9c40e8)、[`a1ab85a`](https://github.com/NoGod3524/EXReader/commit/a1ab85a7a3dbe2542d3a78043a38db08e94559e7)、[`42e362f`](https://github.com/NoGod3524/EXReader/commit/42e362f4d43f8411dd4b83049a0e6e35da75410d)、[`b1e5637`](https://github.com/NoGod3524/EXReader/commit/b1e5637c8f455d5597183889b1dafa5eeb1e6bd1)、[`e8aa242`](https://github.com/NoGod3524/EXReader/commit/e8aa2421338c090707dd9fb20fa9865fcfe09962)、[`be7bdc1`](https://github.com/NoGod3524/EXReader/commit/be7bdc1b9f93debeddeec0b4915ea7de91c271ae)、[`46750e0`](https://github.com/NoGod3524/EXReader/commit/46750e00d5eedcff9c7549dcf83f99a61c9ab5ee)、[`fdcc9e4`](https://github.com/NoGod3524/EXReader/commit/fdcc9e441cc158d5ef19e6e02db30669200d10aa)、[`82d4270`](https://github.com/NoGod3524/EXReader/commit/82d427016a291c4f3809e6ba932c56af40ca0dd5)、[`10d81b3`](https://github.com/NoGod3524/EXReader/commit/10d81b33146fae3c65b67223d0bf88768393a49b)。

### 2.6.0 — FB2、DOCX和RTF结构化解析

中等更新；原提交日期：2026-10-16 / 2026-10-17；历史包声明：0.19.0、0.20.0、0.21.0、0.22.0、0.23.0、0.24.0、0.25.0、0.26.0。

保留FB2图片/封面/表格，DOCX样式/图片/链接/合并格/脚注/列表，以及RTF格式/图片/字体/链接/书签/标题；加入下划线和删除线绘制。

包含提交：[`232d858`](https://github.com/NoGod3524/EXReader/commit/232d85819ee9fecaba330205472bd4cfa72658d8)、[`ad79216`](https://github.com/NoGod3524/EXReader/commit/ad79216b708ae59219a3a19b14acab170e5b9648)、[`7d08c56`](https://github.com/NoGod3524/EXReader/commit/7d08c56b31d76b0949b74c3eae4a950c5866842d)、[`a66e717`](https://github.com/NoGod3524/EXReader/commit/a66e7179c27da74e42d94900439f8f82511114af)、[`a258d60`](https://github.com/NoGod3524/EXReader/commit/a258d60607fc5a04098ca24cb614a01cca8ea6bd)、[`efd8e30`](https://github.com/NoGod3524/EXReader/commit/efd8e30c3c709b4e5b8a67365ca8ef8cd869d458)、[`94226a1`](https://github.com/NoGod3524/EXReader/commit/94226a19e2047c9e84c88cf0f6062fb902bf4421)、[`bdd7803`](https://github.com/NoGod3524/EXReader/commit/bdd780348001f3c24a25e20660ad353584d17bdd)。

### 2.5.0 — 完整阅读会话基础

中等更新；原提交日期：2026-10-16；历史包声明：0.13.0、0.14.0、0.15.0、0.16.0、0.17.0、0.18.0。

接入EPUB作用域字体和CSS字体族、分页检查点恢复、可定位读取、取消/进度、通用导航与EPUB 2 NCX，以及保留结构和资源的EPUB导出；同步当时的版本声明。

包含提交：[`8ba092c`](https://github.com/NoGod3524/EXReader/commit/8ba092cf1a735513bfd564f01445edcbe8f79cf8)、[`bc27700`](https://github.com/NoGod3524/EXReader/commit/bc27700e91f3b95521d70132703f1073ce6bf151)、[`83a18ac`](https://github.com/NoGod3524/EXReader/commit/83a18acaf402356426a89d845ff236d5bec6687a)、[`d21f902`](https://github.com/NoGod3524/EXReader/commit/d21f90270b18d3642e84431b686baf8a3235b19d)、[`7c6ce71`](https://github.com/NoGod3524/EXReader/commit/7c6ce71735b7b0d510f8bcccc00626750b192e02)、[`7364142`](https://github.com/NoGod3524/EXReader/commit/7364142f3ac62b536d8b5ff42a46d96c06444e41)、[`a6ccebc`](https://github.com/NoGod3524/EXReader/commit/a6ccebc83af315324a0b9ef3d8e4b43411cbbaf9)。

### 2.4.1 — 文字、锚点与格式解析审计修复

小缺陷修复；原提交日期：2026-10-16；历史包声明：0.12.0、0.12.1。

修复首行缩进方向、阿拉伯语控制字符上下文、跨行重塑形和长附标工作量；修复重复章节定位、备注写入校验、XML非法字符、RTF fallback计数、HTML raw text及示例并行复制问题，并记录性能与回归结果。

包含提交：[`01beb55`](https://github.com/NoGod3524/EXReader/commit/01beb5554f6b53f8d60bd1e011d997c09725c576)、[`e80a5b9`](https://github.com/NoGod3524/EXReader/commit/e80a5b947181dbe3abeee93710c5a5a23f9fabea)、[`ada8f09`](https://github.com/NoGod3524/EXReader/commit/ada8f090a38d9449d3c88be0eda26f9dfef56feb)、[`f714e66`](https://github.com/NoGod3524/EXReader/commit/f714e66ef4afe6a175998a15594b663ce8f48d6b)、[`a411b4b`](https://github.com/NoGod3524/EXReader/commit/a411b4b02a45658ca581e6f2172fd861bfc3b25d)、[`e37e124`](https://github.com/NoGod3524/EXReader/commit/e37e12497bbdf860dd95824b3ab6bad0f6b2f7c9)、[`237493a`](https://github.com/NoGod3524/EXReader/commit/237493a2fec3203ee63192b0f23e2dd50e0278a2)、[`aa67ecf`](https://github.com/NoGod3524/EXReader/commit/aa67ecf440f3b02f9353974ef109df8756b67834)、[`bb052a5`](https://github.com/NoGod3524/EXReader/commit/bb052a5922f2d69943fd6c3c858d363fd90c79d9)、[`d3feb32`](https://github.com/NoGod3524/EXReader/commit/d3feb32f3d293fb3e02b6e1b2524cc244f10e0fe)、[`5eb289f`](https://github.com/NoGod3524/EXReader/commit/5eb289fb112c553017c2b3fe0b8821673c5868cb)、[`723e6d8`](https://github.com/NoGod3524/EXReader/commit/723e6d89e48adef321a591fd091aa6e61ff3f348)、[`52d0f1e`](https://github.com/NoGod3524/EXReader/commit/52d0f1ef9c11ac24abf642df5882db00808994ee)。

### 2.4.0 — 原生文字塑形与双向排版

中等更新；原提交日期：2026-10-16；历史包声明：0.12.0。

加入原生OpenType替换/定位和Unicode 17双向文字排版。

包含提交：[`c86d50f`](https://github.com/NoGod3524/EXReader/commit/c86d50f97836a2bdd8e877a6c8bd2450f89bf8b7)。

### 2.3.0 — 字素、字体回退与有界分页

中等更新；原提交日期：2026-10-16；历史包声明：0.9.0、0.10.0、0.11.0。

增加Unicode 17字素分析、按字素字体回退、缺字报告、可续排分页和缓存字节预算；建立打开耗时、峰值内存和翻页性能采样，修正测试链接及Darwin内存统计。

包含提交：[`a7de9da`](https://github.com/NoGod3524/EXReader/commit/a7de9dab6c91946acce1035155ca8b77adeeaabb)、[`d41055d`](https://github.com/NoGod3524/EXReader/commit/d41055d46b63a28358e86f8a59ccb21dc0f9f095)、[`99ff236`](https://github.com/NoGod3524/EXReader/commit/99ff236c84ad6637d1453bceacbef0fb87bd5068)、[`1248eb5`](https://github.com/NoGod3524/EXReader/commit/1248eb5c829b9e77966264e3da9dc08240294bef)、[`ae36018`](https://github.com/NoGod3524/EXReader/commit/ae36018e70a3d4fa79788bf51d31d0f16f4b7229)。

### 2.2.1 — Windows SDK示例路径

小缺陷修复；原提交日期：2026-10-16；历史包声明：0.8.0。

修复独立SDK示例对Unicode文件路径的处理。

包含提交：[`6df2134`](https://github.com/NoGod3524/EXReader/commit/6df213473d350b87f01cdb37cdaa2d2c6779a539)。

### 2.2.0 — 开放文档构造、锚点与按需加载

中等更新；原提交日期：2026-10-16；历史包声明：0.6.0、0.7.0、0.8.0。

宿主可构造语义节点、复制资源并提交自定义解析结果；新增可迁移文本锚点、既有标注迁移、索引式EPUB加载和有界阅读会话。

包含提交：[`3e46ee8`](https://github.com/NoGod3524/EXReader/commit/3e46ee86ff68173b753af1b7b71bbc67ef570e81)、[`dbe6e5a`](https://github.com/NoGod3524/EXReader/commit/dbe6e5a96cee30dc55b9a0c71d278c4443141b75)、[`5bbfcdc`](https://github.com/NoGod3524/EXReader/commit/5bbfcdc493e964421dc1b09394ab5615becbc3a1)。

### 2.1.1 — Windows图像分配与运行库链接

小缺陷修复；原提交日期：2026-10-16；历史包声明：0.5.0。

修复MSVC图像内存对齐和MinGW免安装产物的运行库链接。

包含提交：[`fa20e65`](https://github.com/NoGod3524/EXReader/commit/fa20e65eab093126716ecbbe73733dee8096f6c3)。

### 2.1.0 — EPUB文档树与基础图文排版

中等更新；原提交日期：2026-10-15 / 2026-10-16；历史包声明：0.4.0、0.5.0。

保留EPUB章节、元素、属性、资源和链接；增加CSS子集、图片、表格与宿主绘制接口。

包含提交：[`cb13aab`](https://github.com/NoGod3524/EXReader/commit/cb13aabe206cdfa75cc612c9026dc5322fd2b9fa)、[`6974b3c`](https://github.com/NoGod3524/EXReader/commit/6974b3cb86b07cb844b603bdae105bf8f35474c5)。

### 2.0.0 — 将JavaScript底座重写为C11

超大更新；原提交日期：2026-10-15；历史包声明：0.3.0。

主项目改为原生C11引擎、公开C接口与CMake构建，提供基础格式解析、排版、书库及转换；补字体度量缓存、XML深度限制和安装SDK验证。这是底座实现与宿主接入方式的整体重建。

包含提交：[`60e3e03`](https://github.com/NoGod3524/EXReader/commit/60e3e0378d1311deca91710a37d30687e585041a)、[`13ced4b`](https://github.com/NoGod3524/EXReader/commit/13ced4bf79ce83701a7547b642eeb80f8f028d8f)。

### 1.0.0 — 从阅读器拆出无UI框架

超大更新；原提交日期：2026-10-15；历史包声明：0.2.0。

移除主线应用界面与平台壳，重组为可嵌入JavaScript阅读框架和书库API，旧阅读器独立保留；提供独立PDF worker，支持CSP环境。此阶段原创代码使用GPLv3。

包含提交：[`7ff33a1`](https://github.com/NoGod3524/EXReader/commit/7ff33a132dd7971071083e0da0cd310fedc01da3)、[`355f384`](https://github.com/NoGod3524/EXReader/commit/355f384aae7abcb749a27112849e76b7ecc5c760)、[`8b5bb6a`](https://github.com/NoGod3524/EXReader/commit/8b5bb6ae60c6c62d1ad44f8da89174c5b9159f99)、[`5ad64d8`](https://github.com/NoGod3524/EXReader/commit/5ad64d80d6b24f36fed4bdb4219c613c7f8e6d94)、[`4533185`](https://github.com/NoGod3524/EXReader/commit/4533185847a43f64e67d194877bb6bbb4509aed6)。

### 0.2.1 — 阅读视口与预览包修正

小缺陷修复；原提交日期：2026-10-15；历史包声明：0.1.1。

修复阅读视口尺寸，清理重复AppImage构建文件；改进冷启动测试和原生导出/续读验证。原preview-0.1.1产物对应本批。

包含提交：[`ed43882`](https://github.com/NoGod3524/EXReader/commit/ed438829599efd6bc1df12c5c899a2125a2e1cf0)、[`3bdbf26`](https://github.com/NoGod3524/EXReader/commit/3bdbf265bc21b0a7ae02c8688d45c9247ec5ca5f)、[`818a0f9`](https://github.com/NoGod3524/EXReader/commit/818a0f96a0cde860eb4c9886399e8424add2a7da)、[`677c077`](https://github.com/NoGod3524/EXReader/commit/677c077193ade02eb957f97ed7da26f926f2cccd)、[`ac07067`](https://github.com/NoGod3524/EXReader/commit/ac070674634a8988c49585b10dacd7132762232b)。

### 0.2.0 — 跨平台原生打包与系统接入

中等更新；原提交日期：2026-10-15；历史包声明：0.1.0。

补齐桌面及移动构建、原生文件保存、持久化与备份；修正安全区域、Android签名及16 KB对齐、Linux可执行权限，并加入各平台启动与移动文件选择验证。

包含提交：[`7159d5b`](https://github.com/NoGod3524/EXReader/commit/7159d5b1424fb29d7952861b4a08dcc19369897e)、[`c0bfc0f`](https://github.com/NoGod3524/EXReader/commit/c0bfc0fc76768fc20526667b6ba8223ab1ea82ed)、[`2eacf6e`](https://github.com/NoGod3524/EXReader/commit/2eacf6e3a903057bc12b9f98b434b8c79ae4c10c)、[`b8ccffa`](https://github.com/NoGod3524/EXReader/commit/b8ccffae8960d836a95f4bed176eb72ac7fb3f8a)、[`565a3e3`](https://github.com/NoGod3524/EXReader/commit/565a3e399a3caaf82801657e94aefaa3d6d41aa2)、[`200b4b2`](https://github.com/NoGod3524/EXReader/commit/200b4b238c2350439d3871dc00e73ad3d44ab307)、[`2e45266`](https://github.com/NoGod3524/EXReader/commit/2e4526686849cd7d46bac994ef91f0931420c172)、[`87a9a37`](https://github.com/NoGod3524/EXReader/commit/87a9a373480ca998966d9d35cc7f51f57c3079ac)、[`209991f`](https://github.com/NoGod3524/EXReader/commit/209991fe2f0d527ccd667088a30446e52f1f5c4a)、[`15c63ea`](https://github.com/NoGod3524/EXReader/commit/15c63ea2e1c0442784c8e0f3f285ab548b0cabfd)、[`d139af2`](https://github.com/NoGod3524/EXReader/commit/d139af26582a4dcdb839afdd3a3bc692ef0c6f03)、[`469987d`](https://github.com/NoGod3524/EXReader/commit/469987de84e86740af2066a1348c8f3e9da14344)、[`82ab62a`](https://github.com/NoGod3524/EXReader/commit/82ab62a07996a06194bcc1676f19deb7eb5ffb7e)、[`989a556`](https://github.com/NoGod3524/EXReader/commit/989a55678615e248716efc11773d55d168a3e6df)、[`fbed529`](https://github.com/NoGod3524/EXReader/commit/fbed5295ed1643ed6601468d97df46f42ed0aa17)。

### 0.1.0 — 本地优先阅读器

初始版本；原提交日期：2026-10-15；历史包声明：0.1.0。

首次提供带界面阅读器、Windows免安装包与PWA；支持电子书、PDF、有声书、书库、标注、备份及正文格式转换，相关解析和播放使用当时的浏览器/第三方实现。

包含提交：[`647fd06`](https://github.com/NoGod3524/EXReader/commit/647fd064a4c51e44b6a012af770cc45ce83fbb0a)。

## 独立阅读器分支

### 阅读器应用 0.3.0 — 在共享框架上恢复完整界面

中等更新；2026-10-15。该应用有独立版本线，未合入当前C框架。保留原书架和阅读界面，改用当时的共享JavaScript框架，并合入独立PDF worker。历史包声明为0.2.0。

包含专有提交：[`4d8217c`](https://github.com/NoGod3524/EXReader/commit/4d8217cbcaadb3cdc3ffe947c9ce06120b5b84f3)、[`a009d55`](https://github.com/NoGod3524/EXReader/commit/a009d55fedabe5a51e27e0c1582eb9155f00ee90)、[`24a3e04`](https://github.com/NoGod3524/EXReader/commit/24a3e04b6fc456fa3fa68fa7bd6d9cc3b5c4e383)。

原`preview-0.1.0` / `preview-0.1.1`发行附件与旧分支保持原样；新索引只描述其历史归属。

## 全部提交索引

按Git拓扑顺序从旧到新列出，每个不同提交恰好一次。原包声明优先读取该提交的CMake项目版本，JavaScript阶段读取package.json；相同旧编号可能跨多个新批次，应以提交定位。合并提交和被合入提交均列出，变更只在所属批次计一次。

| 提交 | 日期 | 原包声明 | 新版本归属 | 原提交主题 / 变更说明 |
| --- | --- | --- | --- | --- |
| [`647fd06`](https://github.com/NoGod3524/EXReader/commit/647fd064a4c51e44b6a012af770cc45ce83fbb0a) | 2026-10-15 | 0.1.0 | 0.1.0 | Build EXReader local-first reader with Windows portable release and cross-platform core |
| [`7159d5b`](https://github.com/NoGod3524/EXReader/commit/7159d5b1424fb29d7952861b4a08dcc19369897e) | 2026-10-15 | 0.1.0 | 0.2.0 | Build native desktop and mobile artifacts and verify Android in an emulator |
| [`c0bfc0f`](https://github.com/NoGod3524/EXReader/commit/c0bfc0fc76768fc20526667b6ba8223ab1ea82ed) | 2026-10-15 | 0.1.0 | 0.2.0 | Save exports through native system dialogs and validate mobile persistence and backup |
| [`2eacf6e`](https://github.com/NoGod3524/EXReader/commit/2eacf6e3a903057bc12b9f98b434b8c79ae4c10c) | 2026-10-15 | 0.1.0 | 0.2.0 | Keep Android preview signatures stable and bound platform build duration |
| [`b8ccffa`](https://github.com/NoGod3524/EXReader/commit/b8ccffae8960d836a95f4bed176eb72ac7fb3f8a) | 2026-10-15 | 0.1.0 | 0.2.0 | Use native mobile screen size and respect status bar safe area |
| [`565a3e3`](https://github.com/NoGod3524/EXReader/commit/565a3e399a3caaf82801657e94aefaa3d6d41aa2) | 2026-10-15 | 0.1.0 | 0.2.0 | Document platform builds and include verified Apple screenshots and licenses |
| [`200b4b2`](https://github.com/NoGod3524/EXReader/commit/200b4b238c2350439d3871dc00e73ad3d44ab307) | 2026-10-15 | 0.1.0 | 0.2.0 | Check packaged Linux and macOS apps launch on native runners |
| [`2e45266`](https://github.com/NoGod3524/EXReader/commit/2e4526686849cd7d46bac994ef91f0931420c172) | 2026-10-15 | 0.1.0 | 0.2.0 | Build optimized signed Android previews and wait for visible Linux window |
| [`87a9a37`](https://github.com/NoGod3524/EXReader/commit/87a9a373480ca998966d9d35cc7f51f57c3079ac) | 2026-10-15 | 0.1.0 | 0.2.0 | Preserve Android 16 KB native library alignment |
| [`209991f`](https://github.com/NoGod3524/EXReader/commit/209991fe2f0d527ccd667088a30446e52f1f5c4a) | 2026-10-15 | 0.1.0 | 0.2.0 | Record verified native Linux and macOS launch screenshots |
| [`15c63ea`](https://github.com/NoGod3524/EXReader/commit/15c63ea2e1c0442784c8e0f3f285ab548b0cabfd) | 2026-10-15 | 0.1.0 | 0.2.0 | Discover Android WebView sockets and reuse APKs for emulator diagnostics |
| [`d139af2`](https://github.com/NoGod3524/EXReader/commit/d139af26582a4dcdb839afdd3a3bc692ef0c6f03) | 2026-10-15 | 0.1.0 | 0.2.0 | Use Playwright Android API for WebView automation |
| [`469987d`](https://github.com/NoGod3524/EXReader/commit/469987de84e86740af2066a1348c8f3e9da14344) | 2026-10-15 | 0.1.0 | 0.2.0 | Preserve Android test errors before collecting full device logs |
| [`82ab62a`](https://github.com/NoGod3524/EXReader/commit/82ab62a07996a06194bcc1676f19deb7eb5ffb7e) | 2026-10-15 | 0.1.0 | 0.2.0 | Verify signed Android APK through native UI and system file picker |
| [`989a556`](https://github.com/NoGod3524/EXReader/commit/989a55678615e248716efc11773d55d168a3e6df) | 2026-10-15 | 0.1.0 | 0.2.0 | Provide a small Linux archive using system WebKit and verify its executable |
| [`fbed529`](https://github.com/NoGod3524/EXReader/commit/fbed5295ed1643ed6601468d97df46f42ed0aa17) | 2026-10-15 | 0.1.0 | 0.2.0 | Preserve Linux executable mode when packaging on Windows |
| [`ed43882`](https://github.com/NoGod3524/EXReader/commit/ed438829599efd6bc1df12c5c899a2125a2e1cf0) | 2026-10-15 | 0.1.1 | 0.2.1 | Fix reader viewport geometry and prepare 0.1.1 previews |
| [`3bdbf26`](https://github.com/NoGod3524/EXReader/commit/3bdbf265bc21b0a7ae02c8688d45c9247ec5ca5f) | 2026-10-15 | 0.1.1 | 0.2.1 | Verify 0.1.1 native packages and remove duplicate AppImage build files |
| [`818a0f9`](https://github.com/NoGod3524/EXReader/commit/818a0f96a0cde860eb4c9886399e8424add2a7da) | 2026-10-15 | 0.1.1 | 0.2.1 | Dismiss cold-emulator launcher ANR before native reader checks |
| [`677c077`](https://github.com/NoGod3524/EXReader/commit/677c077193ade02eb957f97ed7da26f926f2cccd) | 2026-10-15 | 0.1.1 | 0.2.1 | Retry native UI snapshots while Android activity starts |
| [`ac07067`](https://github.com/NoGod3524/EXReader/commit/ac070674634a8988c49585b10dacd7132762232b) | 2026-10-15 | 0.1.1 | 0.2.1 | Record passing Android 0.1.1 reading persistence and native export checks |
| [`7ff33a1`](https://github.com/NoGod3524/EXReader/commit/7ff33a132dd7971071083e0da0cd310fedc01da3) | 2026-10-15 | 0.2.0 | 1.0.0 | Extract GPLv3 ebook framework with headless library and UI-free renderers |
| [`4d8217c`](https://github.com/NoGod3524/EXReader/commit/4d8217cbcaadb3cdc3ffe947c9ce06120b5b84f3) | 2026-10-15 | 0.2.0 | 阅读器应用 0.3.0 | Restore full GPLv3 reader UI on shared framework APIs |
| [`355f384`](https://github.com/NoGod3524/EXReader/commit/355f384aae7abcb749a27112849e76b7ecc5c760) | 2026-10-15 | 0.2.0 | 1.0.0 | Record framework API checks and ignore generated assets during development |
| [`8b5bb6a`](https://github.com/NoGod3524/EXReader/commit/8b5bb6ae60c6c62d1ad44f8da89174c5b9159f99) | 2026-10-15 | 0.2.0 | 1.0.0 | Isolate framework test artifacts from reader UI checks |
| [`a009d55`](https://github.com/NoGod3524/EXReader/commit/a009d55fedabe5a51e27e0c1582eb9155f00ee90) | 2026-10-15 | 0.2.0 | 阅读器应用 0.3.0 | Keep reader application downstream of the current framework branch |
| [`5ad64d8`](https://github.com/NoGod3524/EXReader/commit/5ad64d80d6b24f36fed4bdb4219c613c7f8e6d94) | 2026-10-15 | 0.2.0 | 1.0.0 | Keep platform build entry points targeting the reader branch |
| [`4533185`](https://github.com/NoGod3524/EXReader/commit/4533185847a43f64e67d194877bb6bbb4509aed6) | 2026-10-15 | 0.2.0 | 1.0.0 | Ship a separate PDF worker for CSP-safe framework embedding |
| [`24a3e04`](https://github.com/NoGod3524/EXReader/commit/24a3e04b6fc456fa3fa68fa7bd6d9cc3b5c4e383) | 2026-10-15 | 0.2.0 | 阅读器应用 0.3.0 | Merge CSP-safe PDF worker support from the framework |
| [`60e3e03`](https://github.com/NoGod3524/EXReader/commit/60e3e0378d1311deca91710a37d30687e585041a) | 2026-10-15 | 0.3.0 | 2.0.0 | Replace primary JavaScript framework with native C11 ebook engine |
| [`13ced4b`](https://github.com/NoGod3524/EXReader/commit/13ced4bf79ce83701a7547b642eeb80f8f028d8f) | 2026-10-15 | 0.3.0 | 2.0.0 | Cache native font metrics, bound XML depth and verify installed SDKs |
| [`cb13aab`](https://github.com/NoGod3524/EXReader/commit/cb13aabe206cdfa75cc612c9026dc5322fd2b9fa) | 2026-10-15 | 0.4.0 | 2.1.0 | Preserve EPUB document trees, resources and chapter links in C |
| [`6974b3c`](https://github.com/NoGod3524/EXReader/commit/6974b3cb86b07cb844b603bdae105bf8f35474c5) | 2026-10-16 | 0.5.0 | 2.1.0 | Add native CSS, image and table flow with open host rendering APIs |
| [`fa20e65`](https://github.com/NoGod3524/EXReader/commit/fa20e65eab093126716ecbbe73733dee8096f6c3) | 2026-10-16 | 0.5.0 | 2.1.1 | Fix MSVC image allocation alignment and portable MinGW runtime linkage |
| [`3e46ee8`](https://github.com/NoGod3524/EXReader/commit/3e46ee86ff68173b753af1b7b71bbc67ef570e81) | 2026-10-16 | 0.6.0 | 2.2.0 | Add generic host document construction with copied resources and semantic nodes |
| [`dbe6e5a`](https://github.com/NoGod3524/EXReader/commit/dbe6e5a96cee30dc55b9a0c71d278c4443141b75) | 2026-10-16 | 0.7.0 | 2.2.0 | Add portable text anchors and migrate persisted annotations |
| [`5bbfcdc`](https://github.com/NoGod3524/EXReader/commit/5bbfcdc493e964421dc1b09394ab5615becbc3a1) | 2026-10-16 | 0.8.0 | 2.2.0 | Add indexed EPUB loading and generic bounded reading sessions |
| [`6df2134`](https://github.com/NoGod3524/EXReader/commit/6df213473d350b87f01cdb37cdaa2d2c6779a539) | 2026-10-16 | 0.8.0 | 2.2.1 | Handle Unicode paths in standalone Windows SDK examples |
| [`a7de9da`](https://github.com/NoGod3524/EXReader/commit/a7de9dab6c91946acce1035155ca8b77adeeaabb) | 2026-10-16 | 0.9.0 | 2.3.0 | Add Unicode 17 grapheme analysis and cluster-safe text layout |
| [`d41055d`](https://github.com/NoGod3524/EXReader/commit/d41055d46b63a28358e86f8a59ccb21dc0f9f095) | 2026-10-16 | 0.10.0 | 2.3.0 | Add host-supplied font fallback with cluster coverage and explicit missing glyphs |
| [`99ff236`](https://github.com/NoGod3524/EXReader/commit/99ff236c84ad6637d1453bceacbef0fb87bd5068) | 2026-10-16 | 0.11.0 | 2.3.0 | Add resumable page layout, byte-bounded caches and measured performance baselines |
| [`1248eb5`](https://github.com/NoGod3524/EXReader/commit/1248eb5c829b9e77966264e3da9dc08240294bef) | 2026-10-16 | 0.11.0 | 2.3.0 | Link pager golden geometry checks with platform math library |
| [`ae36018`](https://github.com/NoGod3524/EXReader/commit/ae36018e70a3d4fa79788bf51d31d0f16f4b7229) | 2026-10-16 | 0.11.0 | 2.3.0 | Expose Darwin peak RSS fields in the native benchmark |
| [`c86d50f`](https://github.com/NoGod3524/EXReader/commit/c86d50f97836a2bdd8e877a6c8bd2450f89bf8b7) | 2026-10-16 | 0.12.0 | 2.4.0 | Add native OpenType shaping and Unicode 17 bidirectional layout |
| [`01beb55`](https://github.com/NoGod3524/EXReader/commit/01beb5554f6b53f8d60bd1e011d997c09725c576) | 2026-10-16 | 0.12.0 | 2.4.1 | Respect paragraph direction for first-line indentation |
| [`e80a5b9`](https://github.com/NoGod3524/EXReader/commit/e80a5b947181dbe3abeee93710c5a5a23f9fabea) | 2026-10-16 | 0.12.0 | 2.4.1 | Copy the Windows example runtime once during parallel builds |
| [`ada8f09`](https://github.com/NoGod3524/EXReader/commit/ada8f090a38d9449d3c88be0eda26f9dfef56feb) | 2026-10-16 | 0.12.0 | 2.4.1 | Preserve Arabic shaping context across invisible bidi controls |
| [`f714e66`](https://github.com/NoGod3524/EXReader/commit/f714e66ef4afe6a175998a15594b663ce8f48d6b) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(shaping): bound mark attachment and source mapping work |
| [`a411b4b`](https://github.com/NoGod3524/EXReader/commit/a411b4b02a45658ca581e6f2172fd861bfc3b25d) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(anchor): compare every repeated chapter occurrence |
| [`e37e124`](https://github.com/NoGod3524/EXReader/commit/e37e12497bbdf860dd95824b3ab6bad0f6b2f7c9) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(library): reject unreadable notes before writing |
| [`237493a`](https://github.com/NoGod3524/EXReader/commit/237493a2fec3203ee63192b0f23e2dd50e0278a2) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(export): reject characters forbidden by XML 1.0 |
| [`aa67ecf`](https://github.com/NoGod3524/EXReader/commit/aa67ecf440f3b02f9353974ef109df8756b67834) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(layout): reshape at committed line boundaries |
| [`bb052a5`](https://github.com/NoGod3524/EXReader/commit/bb052a5922f2d69943fd6c3c858d363fd90c79d9) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(rtf): count control tokens in Unicode fallback |
| [`d3feb32`](https://github.com/NoGod3524/EXReader/commit/d3feb32f3d293fb3e02b6e1b2524cc244f10e0fe) | 2026-10-16 | 0.12.0 | 2.4.1 | fix(html): scan script and style as raw text |
| [`5eb289f`](https://github.com/NoGod3524/EXReader/commit/5eb289fb112c553017c2b3fe0b8821673c5868cb) | 2026-10-16 | 0.12.1 | 2.4.1 | chore(release): document audit fixes in 0.12.1 |
| [`723e6d8`](https://github.com/NoGod3524/EXReader/commit/723e6d89e48adef321a591fd091aa6e61ff3f348) | 2026-10-16 | 0.12.1 | 2.4.1 | docs(performance): record audit fix paging costs |
| [`52d0f1e`](https://github.com/NoGod3524/EXReader/commit/52d0f1ef9c11ac24abf642df5882db00808994ee) | 2026-10-16 | 0.12.1 | 2.4.1 | docs: correct line workspace API link |
| [`8ba092c`](https://github.com/NoGod3524/EXReader/commit/8ba092cf1a735513bfd564f01445edcbe8f79cf8) | 2026-10-16 | 0.13.0 | 2.5.0 | feat(fonts): load scoped EPUB faces and match CSS families |
| [`bc27700`](https://github.com/NoGod3524/EXReader/commit/bc27700e91f3b95521d70132703f1073ce6bf151) | 2026-10-16 | 0.14.0 | 2.5.0 | feat(pager): resume uncached seeks from bounded checkpoints |
| [`83a18ac`](https://github.com/NoGod3524/EXReader/commit/83a18acaf402356426a89d845ff236d5bec6687a) | 2026-10-16 | 0.15.0 | 2.5.0 | feat(io): read indexed EPUBs through seekable sources |
| [`d21f902`](https://github.com/NoGod3524/EXReader/commit/d21f90270b18d3642e84431b686baf8a3235b19d) | 2026-10-16 | 0.16.0 | 2.5.0 | feat(control): add cooperative cancellation and progress |
| [`7c6ce71`](https://github.com/NoGod3524/EXReader/commit/7c6ce71735b7b0d510f8bcccc00626750b192e02) | 2026-10-16 | 0.17.0 | 2.5.0 | feat(navigation): expose generic trees and decode EPUB 2 NCX |
| [`7364142`](https://github.com/NoGod3524/EXReader/commit/7364142f3ac62b536d8b5ff42a46d96c06444e41) | 2026-10-16 | 0.18.0 | 2.5.0 | feat(export): preserve document structure and resources in EPUB |
| [`a6ccebc`](https://github.com/NoGod3524/EXReader/commit/a6ccebc83af315324a0b9ef3d8e4b43411cbbaf9) | 2026-10-16 | 0.18.0 | 2.5.0 | fix(version): synchronize public engine version with 0.18 |
| [`232d858`](https://github.com/NoGod3524/EXReader/commit/232d85819ee9fecaba330205472bd4cfa72658d8) | 2026-10-16 | 0.19.0 | 2.6.0 | feat(fb2): retain images, cover, tables and inline semantics |
| [`ad79216`](https://github.com/NoGod3524/EXReader/commit/ad79216b708ae59219a3a19b14acab170e5b9648) | 2026-10-17 | 0.20.0 | 2.6.0 | feat(docx): decode styles, images, links and merged tables |
| [`7d08c56`](https://github.com/NoGod3524/EXReader/commit/7d08c56b31d76b0949b74c3eae4a950c5866842d) | 2026-10-17 | 0.21.0 | 2.6.0 | feat(docx): retain footnotes, endnotes and reference links |
| [`a66e717`](https://github.com/NoGod3524/EXReader/commit/a66e7179c27da74e42d94900439f8f82511114af) | 2026-10-17 | 0.22.0 | 2.6.0 | feat(docx): retain multilevel lists and numbering state |
| [`a258d60`](https://github.com/NoGod3524/EXReader/commit/a258d60607fc5a04098ca24cb614a01cca8ea6bd) | 2026-10-17 | 0.23.0 | 2.6.0 | feat(rtf): preserve scoped text and paragraph formatting |
| [`efd8e30`](https://github.com/NoGod3524/EXReader/commit/efd8e30c3c709b4e5b8a67365ca8ef8cd869d458) | 2026-10-17 | 0.24.0 | 2.6.0 | feat(rtf): retain embedded pictures and compatibility branches |
| [`94226a1`](https://github.com/NoGod3524/EXReader/commit/94226a19e2047c9e84c88cf0f6062fb902bf4421) | 2026-10-17 | 0.25.0 | 2.6.0 | feat(rtf): retain font names, hyperlinks, bookmarks and title |
| [`bdd7803`](https://github.com/NoGod3524/EXReader/commit/bdd780348001f3c24a25e20660ad353584d17bdd) | 2026-10-17 | 0.26.0 | 2.6.0 | feat(layout): render shared underline and strike decorations |
| [`7566f61`](https://github.com/NoGod3524/EXReader/commit/7566f619b05a87982f49d7655bcc154430da1d36) | 2026-10-17 | 0.27.0 | 2.7.0 | feat(mobi): decode HUFF CDIC and validate record boundaries |
| [`bcce6f0`](https://github.com/NoGod3524/EXReader/commit/bcce6f0d26372a80621adeabd56732f3d5a95176) | 2026-10-17 | 0.28.0 | 2.7.0 | feat(kf8): reconstruct bounded skeleton and fragment chapters |
| [`171120c`](https://github.com/NoGod3524/EXReader/commit/171120c8a0357d8fb4e65781907d7c98bf9c40e8) | 2026-10-17 | 0.29.0 | 2.7.0 | feat(kf8): connect CSS images and bounded native FONT decoding |
| [`a1ab85a`](https://github.com/NoGod3524/EXReader/commit/a1ab85a7a3dbe2542d3a78043a38db08e94559e7) | 2026-10-17 | 0.29.0 | 2.7.0 | test(kf8): terminate binary CSS copies before string assertions |
| [`42e362f`](https://github.com/NoGod3524/EXReader/commit/42e362f4d43f8411dd4b83049a0e6e35da75410d) | 2026-10-17 | 0.30.0 | 2.7.0 | feat(kf8): resolve fragment positions through XML byte anchors |
| [`b1e5637`](https://github.com/NoGod3524/EXReader/commit/b1e5637c8f455d5597183889b1dafa5eeb1e6bd1) | 2026-10-17 | 0.31.0 | 2.7.0 | feat(kf8): preserve authored NCX through shared navigation snapshots |
| [`e8aa242`](https://github.com/NoGod3524/EXReader/commit/e8aa2421338c090707dd9fb20fa9865fcfe09962) | 2026-10-17 | 0.32.0 | 2.7.0 | feat(mobi): select declared KF8 hybrids and reuse shared assets |
| [`be7bdc1`](https://github.com/NoGod3524/EXReader/commit/be7bdc1b9f93debeddeec0b4915ea7de91c271ae) | 2026-10-17 | 0.33.0 | 2.7.0 | feat(kf8): retain guide landmarks and enforce combined navigation budget |
| [`46750e0`](https://github.com/NoGod3524/EXReader/commit/46750e00d5eedcff9c7549dcf83f99a61c9ab5ee) | 2026-10-17 | 0.34.0 | 2.7.0 | feat(kf8): preserve namespaces and connect SVG resource dependencies |
| [`fdcc9e4`](https://github.com/NoGod3524/EXReader/commit/fdcc9e441cc158d5ef19e6e02db30669200d10aa) | 2026-10-17 | 0.35.0 | 2.7.0 | feat(kf8): decode bounded ORDT labels and accept repeated skeleton tuples |
| [`82d4270`](https://github.com/NoGod3524/EXReader/commit/82d427016a291c4f3809e6ba932c56af40ca0dd5) | 2026-10-17 | 0.36.0 | 2.7.0 | feat(mobi): decode native titles and retain declared covers |
| [`10d81b3`](https://github.com/NoGod3524/EXReader/commit/10d81b33146fae3c65b67223d0bf88768393a49b) | 2026-10-17 | 0.37.0 | 2.7.0 | feat(library): import bounded declared covers atomically |
| [`12f12cf`](https://github.com/NoGod3524/EXReader/commit/12f12cf20c10414d3a2463a5da6ab5726f342977) | 2026-10-17 | 0.38.0 | 3.0.0 | feat(layout): add bounded format-neutral positioned paint model |
| [`3301cf3`](https://github.com/NoGod3524/EXReader/commit/3301cf359168b6e184260df9d7ca89727845719c) | 2026-10-17 | 0.39.0 | 3.0.0 | feat(pdf): add bounded native object and classic xref parser |
| [`2ac097a`](https://github.com/NoGod3524/EXReader/commit/2ac097ae53e18241254432fb3ac26ed29ee6f0d9) | 2026-10-17 | 0.40.0 | 3.0.0 | feat(pdf): load xref streams hybrid revisions and compressed objects |
| [`6018c88`](https://github.com/NoGod3524/EXReader/commit/6018c881493fb3b233d6765734327fe379e74b9f) | 2026-10-17 | 0.41.0 | 3.0.0 | feat(pdf): decode filter chains and PNG TIFF predictors |
| [`605a50f`](https://github.com/NoGod3524/EXReader/commit/605a50fdaa8c69f1880a59153f3268c0f1583e38) | 2026-10-17 | 0.42.0 | 3.0.0 | feat(pdf): decode bounded LZW with both early-change modes |
| [`aaebfa0`](https://github.com/NoGod3524/EXReader/commit/aaebfa01fc73d5624edcb4a187b63ac0a8a9e2b7) | 2026-10-17 | 0.43.0 | 3.0.0 | feat(pdf): read bounded inherited page trees and lazy content arrays |
| [`03778cc`](https://github.com/NoGod3524/EXReader/commit/03778cc65adefb79c9f0dc345e79618d65cc1582) | 2026-10-17 | 0.44.0 | 3.0.0 | feat(pdf): walk content operators with bounded reusable operand arenas |
| [`477d357`](https://github.com/NoGod3524/EXReader/commit/477d35758f12c03465324a8c2cadc96869107b1c) | 2026-10-17 | 0.45.0 | 3.0.0 | feat(pdf): decode bounded variable-width ToUnicode CMaps |
| [`3255a25`](https://github.com/NoGod3524/EXReader/commit/3255a25535e2e1088429509ceb47da430c437335) | 2026-10-17 | 0.46.0 | 3.0.0 | feat(pdf): read font programs CID glyph maps and horizontal vertical metrics |
| [`325a7f0`](https://github.com/NoGod3524/EXReader/commit/325a7f0a4764eaf651133f7c466aec9635b52500) | 2026-10-17 | 0.47.0 | 3.0.0 | feat(pdf): execute bounded text state and stream affine glyph geometry |
| [`9a35ebb`](https://github.com/NoGod3524/EXReader/commit/9a35ebb44f75e87f90516b639a53b701d81b4b25) | 2026-10-17 | 0.48.0 | 3.0.0 | feat(pdf): execute bounded nested Form text with isolated graphics state |
| [`47c50b9`](https://github.com/NoGod3524/EXReader/commit/47c50b9e2679cc57d92ce41ef53fd3f6a554bee4) | 2026-10-17 | 0.49.0 | 3.0.0 | feat(font): support format-neutral scalable glyph-only font sets |
| [`cf835bb`](https://github.com/NoGod3524/EXReader/commit/cf835bb001a09a3329fd8f600454bd7dfe12829b) | 2026-10-17 | 0.50.0 | 3.0.0 | feat(vector): add bounded native antialiased fill and clip-mask rasterization |
| [`2a72314`](https://github.com/NoGod3524/EXReader/commit/2a72314c44e7bce1217329f9d28c37f97e217132) | 2026-10-17 | 0.51.0 | 3.0.0 | feat(vector): flatten transformed quadratic cubic paths with bounded adaptive subdivision |
| [`ff33a4b`](https://github.com/NoGod3524/EXReader/commit/ff33a4b6384b30c2cd69334d9056071f0c7922ec) | 2026-10-17 | 0.52.0 | 3.0.0 | feat(vector): construct bounded caps joins miter limits and affine stroke outlines |
| [`4b20178`](https://github.com/NoGod3524/EXReader/commit/4b201785c42116b809acc9a3f29c7bbd06269da1) | 2026-10-17 | 0.53.0 | 3.0.0 | feat(vector): split bounded dash patterns phases dots and closed seams |
| [`ba0b13f`](https://github.com/NoGod3524/EXReader/commit/ba0b13fc413f0a6c4626476f51208cc0d3d4c6fe) | 2026-10-17 | 0.54.0 | 3.0.0 | feat(pdf): unify drawing state paths clipping and native vector events |
| [`79c8cd3`](https://github.com/NoGod3524/EXReader/commit/79c8cd3a3c53029f6a1034588090759df678c0a7) | 2026-10-17 | 0.55.0 | 3.0.0 | Add native PDF encoding mappings and standard font metrics |
| [`e84c996`](https://github.com/NoGod3524/EXReader/commit/e84c996a81cb7cb025601e6e41b67320b02e7d1f) | 2026-10-17 | 0.56.0 | 3.0.0 | Render native PDF glyph outlines with independent glyph selection |
| [`d3435f9`](https://github.com/NoGod3524/EXReader/commit/d3435f99022fcb935321b5d60485ad762dab8c5c) | 2026-10-17 | 0.57.0 | 3.0.0 | Integrate native PDF text and vector raster backend with shared clipping |
| [`b536469`](https://github.com/NoGod3524/EXReader/commit/b536469560e2a8a2a3c1cdd4c1bff99dcb0dde33) | 2026-10-17 | 0.58.0 | 3.0.0 | Decode packed PDF images and paint affine RGBA images natively |
| [`99ee06d`](https://github.com/NoGod3524/EXReader/commit/99ee06d95f298b97072d64a2634c5c2c2a237d1e) | 2026-10-17 | 0.59.0 | 3.0.0 | Decode terminal PDF JPEG streams through the existing bounded image codec |
| [`154a2d9`](https://github.com/NoGod3524/EXReader/commit/154a2d9acd873469086a894dbdac93a460b20b06) | 2026-10-17 | 0.60.0 | 3.0.0 | Preserve independent PDF image masks and support indexed colors and mattes |
| [`dd68de3`](https://github.com/NoGod3524/EXReader/commit/dd68de3e94b753caadff2ed9212e5c141bf39262) | 2026-10-17 | 0.61.0 | 3.0.0 | Add generic bidirectional page viewports and cropped PDF page rasterization |
| [`f080abd`](https://github.com/NoGod3524/EXReader/commit/f080abd20cfaac246bae338fe342b383bc702cea) | 2026-10-17 | 0.62.0 | 3.0.0 | Expose a format-independent C canvas and reuse it for PDF rendering |
| [`dcb66ab`](https://github.com/NoGod3524/EXReader/commit/dcb66abf5291fb2da5b04b04dd58264f9c5d4089) | 2026-10-17 | 0.63.0 | 3.0.0 | Expose owned glyph outlines for host and canvas rendering |
| [`8031631`](https://github.com/NoGod3524/EXReader/commit/8031631d3260aba27b6ef20caf0dacb678e5f2af) | 2026-10-17 | 0.64.0 | 3.0.0 | Decouple PDF painting through public streaming drawing consumers |
| [`ed66563`](https://github.com/NoGod3524/EXReader/commit/ed66563635c1ebdcdd810df44571cfb5132ad104) | 2026-10-17 | 0.65.0 | 3.0.0 | Add format-independent on-demand fixed page documents |
| [`b167c58`](https://github.com/NoGod3524/EXReader/commit/b167c588907371e3a4c9ca19389c17d7ce6f4197) | 2026-10-17 | 0.66.0 | 3.0.0 | Open and render PDF through the public fixed-page SDK |
| [`06bcf9f`](https://github.com/NoGod3524/EXReader/commit/06bcf9fd4d58da41a99fc9f1481696c58960fc4d) | 2026-10-17 | 0.67.0 | 3.0.0 | Add format-independent owned fixed page text snapshots |
| [`4c5980b`](https://github.com/NoGod3524/EXReader/commit/4c5980bda82a8ae7bbf7a830c34510faa3496a6e) | 2026-10-17 | 0.68.0 | 3.0.0 | Expose PDF semantic text and logical page quads through fixed SDK |
| [`dacd144`](https://github.com/NoGod3524/EXReader/commit/dacd14479e3c86eba693d851ebd327df22d1598a) | 2026-10-17 | 0.69.0 | 3.0.0 | Add linear fixed text search, quad hits and whole-region selection |
| [`934dd91`](https://github.com/NoGod3524/EXReader/commit/934dd9108b771c6566d13621442d25e498d9c98f) | 2026-10-17 | 0.70.0 | 3.0.0 | Add page-scoped stable fixed text annotation anchors |
| [`792076e`](https://github.com/NoGod3524/EXReader/commit/792076e0b500fbfb952ffd2e30eb054e60ff3b8e) | 2026-10-17 | 0.71.0 | 3.0.0 | Persist PDF books, page progress and stable fixed-page notes |
| [`b6b31d7`](https://github.com/NoGod3524/EXReader/commit/b6b31d7561fe88df96ede087d35294f8a8775746) | 2026-10-17 | 0.72.0 | 3.1.0 | Add open audio timelines, chapters and bidirectional text synchronization |
| [`de65c24`](https://github.com/NoGod3524/EXReader/commit/de65c245923db0a6a284855ab3dedc061d4199f9) | 2026-10-17 | 0.73.0 | 3.1.0 | Add lazy host audio playback controls and stable track resume |
| [`a0ddece`](https://github.com/NoGod3524/EXReader/commit/a0ddecefec342b802c30dcb4f0351c6b8def958e) | 2026-10-17 | 0.74.0 | 3.1.0 | Decode WAVE PCM on demand through bounded 64-bit random sources |
| [`c8f07c3`](https://github.com/NoGod3524/EXReader/commit/c8f07c33192b32d88d7da5996cc02a1f78e0d4f1) | 2026-10-17 | 0.75.0 | 3.1.0 | Persist full-range audio resume points and time bookmarks |
| [`333f2e2`](https://github.com/NoGod3524/EXReader/commit/333f2e2776a1f5beb7777083792fb7895ee55243) | 2026-10-17 | 0.76.0 | 3.1.0 | Verify WAVE decoding from standalone installed SDK host examples |
| [`f5e92f1`](https://github.com/NoGod3524/EXReader/commit/f5e92f12d39e778c08c977abfa729081351ec9a3) | 2026-10-17 | 0.77.0 | 3.1.0 | Expose Swift C module and owned PDF text font and PCM wrappers |
| [`2aa97a9`](https://github.com/NoGod3524/EXReader/commit/2aa97a96dffcc2792439794994158b41f7eb7fea) | 2026-10-17 | 0.78.0 | 3.1.0 | Add optional owned JNI PDF and WAVE adapters for Java and Android |
| [`c0c9808`](https://github.com/NoGod3524/EXReader/commit/c0c980815047ddd0c95e1adae0bcc2aa44b88639) | 2026-10-17 | 0.79.0 | 3.2.0 | Preserve RTF table rows and cells through layout and EPUB export |
| [`adfd228`](https://github.com/NoGod3524/EXReader/commit/adfd228bdc3734b7bc84d92d89d32b3539a306c0) | 2026-10-17 | 0.80.0 | 3.2.0 | Preserve RTF horizontal vertical and rectangular table merges |
| [`fd411e4`](https://github.com/NoGod3524/EXReader/commit/fd411e442e11046e84eebc941f7d75588303a24b) | 2026-10-17 | 0.81.0 | 3.2.0 | Preserve RTF footnotes endnotes and bidirectional references |
| [`0c311d8`](https://github.com/NoGod3524/EXReader/commit/0c311d8d7fbfc233274f399e8acad47fbe2b51e6) | 2026-10-17 | 0.82.0 | 3.2.0 | Preserve RTF list hierarchy and supplied numbering labels |
| [`4973ea6`](https://github.com/NoGod3524/EXReader/commit/4973ea61d42aa275e0da5f55bde6fbfbd3e8b750) | 2026-10-17 | 0.83.0 | 3.2.0 | feat(rtf): generate multi-level list numbering and overrides |
| [`8292325`](https://github.com/NoGod3524/EXReader/commit/82923253baef96a972e14e4f6c77d06036981604) | 2026-10-17 | 0.84.0 | 3.2.0 | feat(export): preserve chapters and assets in HTML directory bundles |
| [`713c2a8`](https://github.com/NoGod3524/EXReader/commit/713c2a8b777bbaafcbac91b141dacbe87536e1e5) | 2026-10-17 | 0.85.0 | 3.2.0 | feat(library): add atomic exact-source unique import |
| [`5db01d0`](https://github.com/NoGod3524/EXReader/commit/5db01d08e766dcbaf2a328dfe45bd36c42cce172) | 2026-10-17 | 0.86.0 | 3.3.0 | feat(cfi): add native chapter DOM path creation and resolution |
| [`27746e4`](https://github.com/NoGod3524/EXReader/commit/27746e4892bd8976d0ce67ff7585a4f102dda1b7) | 2026-10-17 | 0.87.0 | 3.3.0 | feat(cfi): address original EPUB spine entries with full point CFIs |
| [`2135309`](https://github.com/NoGod3524/EXReader/commit/2135309aa4394247036145eb2393aac60ae328a9) | 2026-10-17 | 0.88.0 | 3.3.0 | feat(cfi): resolve EPUB positions by loading only their target chapter |
| [`ab8550e`](https://github.com/NoGod3524/EXReader/commit/ab8550e6b1826672637141babd379d84e9ec6204) | 2026-10-17 | 0.89.0 | 3.3.0 | feat(cfi): support canonical simple ranges and corrected endpoint ordering |
| [`fb49403`](https://github.com/NoGod3524/EXReader/commit/fb4940304edbe34b55bf657e41a1fa92a5e43405) | 2026-10-17 | 0.90.0 | 3.3.0 | feat(cfi): validate and generate text assertions with unique context recovery |
| [`7dc8d8a`](https://github.com/NoGod3524/EXReader/commit/7dc8d8a9a136cc3258a7348f151e13ff32f7e3f1) | 2026-10-17 | 0.91.0 | 3.4.0 | feat(sdk): define ABI epoch and export relocatable CMake consumer package |
| [`891f818`](https://github.com/NoGod3524/EXReader/commit/891f8187ebf2b13d934ef3b0ae7794055637015e) | 2026-10-17 | 0.92.0 | 3.4.0 | feat(search): add optional persistent format-neutral text indexing |
| [`1d30b03`](https://github.com/NoGod3524/EXReader/commit/1d30b03d077300c2e1e12885bfaf9ecedfdb09bf) | 2026-10-17 | 0.93.0 | 3.4.0 | feat(search): rebuild complete sources atomically through streaming providers |
| [`695d092`](https://github.com/NoGod3524/EXReader/commit/695d0921c2fa2cee082a959365658464329443ff) | 2026-10-17 | 0.94.0 | 3.4.0 | feat(library): persist stable reading-position selectors atomically |
| [`a0a50a1`](https://github.com/NoGod3524/EXReader/commit/a0a50a1bd42f19ccc8ca1864aaffff4b1576071a) | 2026-10-17 | 0.95.0 | 3.4.0 | feat(library): atomically reproject books and relocate annotations and progress |
| [`17a826d`](https://github.com/NoGod3524/EXReader/commit/17a826d91552ae93bfdc94e4505e831159c78071) | 2026-10-17 | 0.96.0 | 3.4.0 | feat(annotation): exchange plain-text Web Annotations with quote selectors |
| [`07d952f`](https://github.com/NoGod3524/EXReader/commit/07d952ff5518f03f9707120dbfad27444ebf26d5) | 2026-10-17 | 0.97.0 | 3.5.0 | feat(pdf): expose lazy generic metadata and import Info title and author |
| [`520db83`](https://github.com/NoGod3524/EXReader/commit/520db835dc0b79c6d9729dc7b602fed811978ecd) | 2026-10-17 | 0.98.0 | 3.5.0 | feat(metadata): parse reusable XMP literals and merge PDF metadata |
| [`9c7f186`](https://github.com/NoGod3524/EXReader/commit/9c7f1865f66a559ad0d68ef19d0cf3dad38a993c) | 2026-10-17 | 0.99.0 | 3.5.0 | feat(bindings): expose owned PDF and XMP metadata in Swift and Java |
| [`5e0d2d9`](https://github.com/NoGod3524/EXReader/commit/5e0d2d941690781d514db462c62b02213244a1b3) | 2026-10-17 | 0.99.0 | 3.5.0 | fix(swift): avoid metadata fixture variable collision in host checks |
| [`6ed05b0`](https://github.com/NoGod3524/EXReader/commit/6ed05b09b08fa260fdb4dc7d4a9e05a3a8b324be) | 2026-10-17 | 0.100.0 | 3.5.0 | feat(pdf): read native page annotations through generic owned snapshots |
| [`5a756d6`](https://github.com/NoGod3524/EXReader/commit/5a756d6d54c92c134192c40c8951cdc52c684726) | 2026-10-17 | 0.18.0 | 3.5.0 | chore(version): consolidate development steps into milestone 0.18.0 |
| [`5ff51c3`](https://github.com/NoGod3524/EXReader/commit/5ff51c3b0fbe02fe0fade0940c748658e06f3369) | 2026-10-17 | 0.18.0 | 3.6.0 | feat(pdf): write native notes and highlights as incremental revisions |
| [`590385d`](https://github.com/NoGod3524/EXReader/commit/590385d03a9cf7ad07fe9ef33a39c38b1dd38712) | 2026-10-17 | 0.18.0 | 3.6.0 | docs: record PDF annotation writer platform validation [skip ci] |
| [`3b27c84`](https://github.com/NoGod3524/EXReader/commit/3b27c84744bb082b09a673e9c417d5bd71c49f3b) | 2026-10-17 | 0.18.0 | 3.6.0 | feat(core): complete default Unicode line breaking and add native audio paths |
| [`888fc49`](https://github.com/NoGod3524/EXReader/commit/888fc491adce0974f179bd1f7ad3d9665a1ce7a3) | 2026-10-17 | 0.18.0 | 3.7.0 | feat(core): add gapless MP3, soft hyphens and PDF metadata updates |
| [`3b1a905`](https://github.com/NoGod3524/EXReader/commit/3b1a9050c852d07b2b2f1e0e92c31a776053bad5) | 2026-10-17 | 0.18.0 | 3.7.0 | fix(test): include integer limits for soft hyphen checks |
| [`4b3d166`](https://github.com/NoGod3524/EXReader/commit/4b3d16640411cbd1ead93e3114612af2b9c4ccd8) | 2026-10-17 | 0.18.0 | 3.7.0 | fix(test): link soft hyphen geometry checks with libm |
| [`a1a1e4d`](https://github.com/NoGod3524/EXReader/commit/a1a1e4d2318c493e70fa5f9226f1654f405b084a) | 2026-10-17 | 0.18.0 | 3.8.0 | feat(core): add vertical layout, Type3 fonts, AAC/M4B and EPUB editing |
| [`5e82ba3`](https://github.com/NoGod3524/EXReader/commit/5e82ba3114025e4bed2ef6e160b2a7f8ae94c516) | 2026-10-17 | 0.18.0 | 3.8.0 | fix(test): terminate extracted XML and initialize BMFF table rows |
| [`0f45262`](https://github.com/NoGod3524/EXReader/commit/0f45262b6e6531720c23953f80acaa7fb08e4c0c) | 2026-10-17 | 0.18.0 | 3.9.0 | feat(core): add mixed writing contexts, variable fonts, WSOLA and inline PDF images |
| [`55fb274`](https://github.com/NoGod3524/EXReader/commit/55fb27456162517eaf22bcf0b629722e2546cf2c) | 2026-10-17 | 0.18.0 | 3.9.0 | feat(core): add Devanagari, ruby, calibrated PDF colors and mobile reflow APIs |
| [`7ea57fc`](https://github.com/NoGod3524/EXReader/commit/7ea57fcd1522b83b7a46a48840b6428b3ca55ede) | 2026-10-17 | 0.18.0 | 3.9.0 | feat(audio): inspect M4B metadata, covers and chapters without AAC |
| [`43ef9ac`](https://github.com/NoGod3524/EXReader/commit/43ef9ac2f168c5a3fcc09d3641fad38d537721ad) | 2026-10-17 | 0.18.0 | 3.9.1 | fix(swift): preserve glyph-only font support in reflow adapter |
| [`c59d1b8`](https://github.com/NoGod3524/EXReader/commit/c59d1b850bae8ee652e578f5a5771863aee43ec7) | 2026-10-17 | 0.18.0 | 3.10.0 | feat(pdf): render Separation colors with exponential and stitching functions |
| [`fa2942f`](https://github.com/NoGod3524/EXReader/commit/fa2942fdfaa24d3dda136f7da5f89f142723bf9c) | 2026-10-17 | 0.18.0 | 3.10.0 | feat(pdf): evaluate packed linear sampled tint functions |
| [`847de68`](https://github.com/NoGod3524/EXReader/commit/847de68ee9a6e378765c6d2c094e614be62170b7) | 2026-10-17 | 0.18.0 | 3.10.0 | feat(pdf): evaluate bounded Type 4 calculator tint functions |
| [`98ab5f2`](https://github.com/NoGod3524/EXReader/commit/98ab5f26145b1cc64eaf4df219f75a7466aedc0b) | 2026-10-17 | 0.18.0 | 3.10.0 | feat(audio): inspect referenced QuickTime chapter tracks |
| [`58e907f`](https://github.com/NoGod3524/EXReader/commit/58e907f0df4919b16cf0803b244c77666f48e7fd) | 2026-10-17 | 0.18.0 | 3.10.0 | feat(audio): preserve mdta and freeform text metadata |
| [`f07af93`](https://github.com/NoGod3524/EXReader/commit/f07af935e3398a6e66b17f3c40c2881905c02426) | 2026-10-17 | 0.18.0 | 3.11.0 | feat(text): render COLR v0 glyphs and expose color layers |
| [`77bfa02`](https://github.com/NoGod3524/EXReader/commit/77bfa022cc6eb9baa2536ffe67853c6e5f765863) | 2026-10-17 | 0.18.0 | 3.11.0 | feat(text): decode and render native sbix bitmap glyphs |
| [`126b1e0`](https://github.com/NoGod3524/EXReader/commit/126b1e0332ce24cbee0d046b7d5879e5cd74beb0) | 2026-10-17 | 0.18.0 | 3.11.0 | fix(text): load embedded sbix fonts through the common face opener |
| [`3f8547d`](https://github.com/NoGod3524/EXReader/commit/3f8547d80fdde61a804a631786dd25a6d1c951fd) | 2026-10-17 | 0.18.0 | 3.11.0 | Support native CBDT/CBLC bitmap-only fonts |
| [`504e463`](https://github.com/NoGod3524/EXReader/commit/504e463341cc2709731c8b7be8feb23a5b919519) | 2026-10-17 | 0.18.0 | 3.11.0 | Match explicit invisible OpenType components in emoji sequences |
| [`9f52053`](https://github.com/NoGod3524/EXReader/commit/9f520533787e0e5371f4d6679c947103f5b911e7) | 2026-10-17 | 0.18.0 | 3.11.0 | Support Unicode variation sequences and font fallback |
| [`7e2b55c`](https://github.com/NoGod3524/EXReader/commit/7e2b55c9681aefb0ea27d2a15db4593da5945110) | 2026-10-17 | 0.18.0 | 3.12.0 | Render PDF registration All with additive-device tint semantics |
| [`f3727ea`](https://github.com/NoGod3524/EXReader/commit/f3727ea2dab3a15790e377f6e9fd6110d812e5b7) | 2026-10-17 | 0.18.0 | 3.12.0 | Support 32-input PDF Type 4 functions and DeviceN composite color |
| [`6731b1b`](https://github.com/NoGod3524/EXReader/commit/6731b1ba904402f529023ad516ebf5c1c11efd77) | 2026-10-17 | 0.18.0 | 3.12.0 | Record verified native color and font builds [skip ci] |
| [`3ea8bca`](https://github.com/NoGod3524/EXReader/commit/3ea8bca3618bed4f4718c445f8317351e27f9601) | 2026-10-17 | 0.18.0 | 3.12.0 | Support multidimensional and cubic PDF sampled functions |
| [`e7ce3ce`](https://github.com/NoGod3524/EXReader/commit/e7ce3ce9c9155c19f957c0fc8d3d7ceb3cbded52) | 2026-10-17 | 0.18.0 | 3.13.0 | Add native CBZ fixed pages and bookshelf integration |
| [`06893f3`](https://github.com/NoGod3524/EXReader/commit/06893f3d6d87d7770590d095659bdb4f6fca917b) | 2026-10-17 | 0.18.0 | 3.13.0 | Convert PDF ICCBased profiles with bounded native color contexts |
| [`a4e70f6`](https://github.com/NoGod3524/EXReader/commit/a4e70f6a6a97e0fa5d8f3e0c992f7ba970440f75) | 2026-10-17 | 0.18.0 | 3.13.0 | Keep statically embedded ICC symbols private |
| [`166e5ad`](https://github.com/NoGod3524/EXReader/commit/166e5ad7ebb897d5ff01e7e4d69f645d107caf25) | 2026-10-17 | 0.18.0 | 3.13.0 | Record final ICC platform verification and pause checkpoint [skip ci] |
| [`aa3a329`](https://github.com/NoGod3524/EXReader/commit/aa3a32902335fb15ea8f0e0803900ace98ba0c77) | 2026-10-17 | 0.18.0 | 3.14.0 | Preserve PDF CMYK and YCCK JPEG samples through color conversion |
| [`65c32d9`](https://github.com/NoGod3524/EXReader/commit/65c32d9f4bda5e7ab4e390a455f480d266cb2785) | 2026-10-17 | 0.18.0 | 3.15.0 | Read Standard-security PDF R2-R6 with retryable password authentication |
| [`d4d8fb3`](https://github.com/NoGod3524/EXReader/commit/d4d8fb3e2e14f43f7544bea1caf06839eb5c8883) | 2026-10-17 | 0.18.0 | 3.16.0 | Allocate declared EPUB table column widths and preserve checkpoint geometry |
| [`a99f125`](https://github.com/NoGod3524/EXReader/commit/a99f1254252cbdef1af94f652530d54dbefb72bf) | 2026-10-17 | 0.18.0 | 3.16.0 | Measure intrinsic EPUB table widths through native shaping and line breaking |
| [`a0117c7`](https://github.com/NoGod3524/EXReader/commit/a0117c741d5fe7dc2c3270dc5480cf9a15cc8c5c) | 2026-10-17 | 0.18.0 | 3.16.0 | Align EPUB table cells by baseline and block axis with height constraints |
| [`57c9f17`](https://github.com/NoGod3524/EXReader/commit/57c9f17fb07adc4d71087c788a3cf30cadc6823f) | 2026-10-17 | 0.18.0 | 3.16.0 | Collapse shared EPUB table borders with half-width geometry and portable paint layers |
| [`7abacb9`](https://github.com/NoGod3524/EXReader/commit/7abacb9d45e4dc3bd4a5377eefe149243d176ef2) | 2026-10-17 | 0.18.0 | 3.17.0 | Lay out native CSS floats with dynamic line corridors and recoverable source positions |
| [`98e4250`](https://github.com/NoGod3524/EXReader/commit/98e4250702e43f1d6b256ce7da26ac5ebbc4b876) | 2026-10-17 | 0.18.0 | 3.17.0 | Record committed source hashes for float benchmark reproduction [skip ci] |
| [`a94ca62`](https://github.com/NoGod3524/EXReader/commit/a94ca62d3739a7f6c5317f49772c52c0ab7c428c) | 2026-10-17 | 0.18.0 | 3.17.0 | Bound generic flow unit nesting for floats and table cells |
| [`9ec2349`](https://github.com/NoGod3524/EXReader/commit/9ec2349c51c6030a39b6497ebff652494bd12e3f) | 2026-10-18 | 0.18.0 | 3.17.0 | Stream long native floats through bounded page cursors and checkpoints |
| [`2849fa6`](https://github.com/NoGod3524/EXReader/commit/2849fa67963f56b9bdcb077d36eb9c0697fd9ca1) | 2026-10-18 | 0.18.0 | 3.17.0 | Record passing float streaming CI and exact benchmark source commit [skip ci] |
| [`5fe3ca9`](https://github.com/NoGod3524/EXReader/commit/5fe3ca90c1167d497300e57ff333c00c2c308ab1) | 2026-10-18 | 0.18.0 | 3.17.0 | Place ordinary table BFCs beside floats with stable paginated columns |
| [`4c9c19f`](https://github.com/NoGod3524/EXReader/commit/4c9c19f7ed2fb9e1b2d7a7692c2ecc92d412d5eb) | 2026-10-18 | 0.18.0 | 3.17.0 | Record passing table BFC CI and benchmark source provenance [skip ci] |
| [`e9e3b64`](https://github.com/NoGod3524/EXReader/commit/e9e3b64d5cfa578d9ab224302fc5c12666a4da94) | 2026-10-18 | 0.18.0 | 3.18.0 | Add optional native language pattern dictionaries and safe hyphenation providers |
| [`6d14acf`](https://github.com/NoGod3524/EXReader/commit/6d14acf5586c38977bc948dab8d0fff3d212b04b) | 2026-10-18 | 0.18.0 | 3.18.0 | Clarify break-only provider contract and record dictionary CI provenance [skip ci] |
| [`daa7cc5`](https://github.com/NoGod3524/EXReader/commit/daa7cc570d6bc4edc49490b3b0c2035b06b70069) | 2026-10-18 | 0.18.0 | 3.18.0 | feat: integrate optional dictionary hyphenation into native layout |
| [`ac0a003`](https://github.com/NoGod3524/EXReader/commit/ac0a0032caca58d45506a6be43323ab143c1cf29) | 2026-10-18 | 0.18.0 | 3.18.0 | docs: record cross-platform automatic hyphenation verification [skip ci] |
| [`1eb9f0d`](https://github.com/NoGod3524/EXReader/commit/1eb9f0ddef27f5a5c7c7ffd777132eaacc1f1352) | 2026-10-18 | 0.18.0 | 3.18.0 | feat: normalize native hyphenation with Unicode 17 source mapping |
| [`249f756`](https://github.com/NoGod3524/EXReader/commit/249f756f233340826e6f7add5c21b650f662a24e) | 2026-10-18 | 0.18.0 | 3.18.0 | docs: record canonical hyphenation platform verification [skip ci] |
| [`5037678`](https://github.com/NoGod3524/EXReader/commit/5037678dec997515814af6e61beb6c6984b8496d) | 2026-10-18 | 0.18.0 | 3.18.0 | feat: support native compound hyphenation with bounded recursive rules |
| [`418c33d`](https://github.com/NoGod3524/EXReader/commit/418c33d8ab233888e3cdbe0684bf5b534871dd6b) | 2026-10-18 | 0.18.0 | 3.18.0 | docs: record compound dictionary platform verification [skip ci] |
| [`8067ede`](https://github.com/NoGod3524/EXReader/commit/8067ede251d9a3298c07e33f33b5e59e4aaaed3f) | 2026-10-18 | 0.18.0 | 3.19.0 | feat: expose owned discretionary hyphenation queries and providers |
| [`5b1aa4b`](https://github.com/NoGod3524/EXReader/commit/5b1aa4b35f2cc75c5a1402a25736eb94d78f55ff) | 2026-10-18 | 0.18.0 | 3.19.0 | docs: record discretionary query platform verification [skip ci] |
| [`fd95ac4`](https://github.com/NoGod3524/EXReader/commit/fd95ac43ab0585ea4fead7f48c9dd2c39c77f1a6) | 2026-10-18 | 0.18.0 | 3.19.0 | feat: render discretionary replacements through native page reflow |
| [`4ee3923`](https://github.com/NoGod3524/EXReader/commit/4ee39235cf49e723b2f6a975cf3948873c430dcf) | 2026-10-18 | 0.18.0 | 3.19.0 | fix: preserve source progress after zero-cut word insertions |
| [`66b71a8`](https://github.com/NoGod3524/EXReader/commit/66b71a87296662e723b6332b7681ed30f1199380) | 2026-10-18 | 0.18.0 | 3.19.0 | docs: record verified replacement reflow and insertion correction [skip ci] |
| [`f27ace2`](https://github.com/NoGod3524/EXReader/commit/f27ace2ca341c26dd94de055a068013651182e1e) | 2026-10-18 | 0.18.0 | 3.19.0 | feat: rematch changed word remainders through mapped source positions |
| [`d3c4d75`](https://github.com/NoGod3524/EXReader/commit/d3c4d75afd120e6d6b99e7576e1d912e5876cc78) | 2026-10-18 | 0.18.0 | 3.19.0 | docs: record verified mapped remainder reflow [skip ci] |
| [`ddeae97`](https://github.com/NoGod3524/EXReader/commit/ddeae9735ee33266e0144b2a6496d8f1d19aa8af) | 2026-10-18 | 0.18.0 | 3.19.1 | fix: replay Unicode display boundaries after spelling replacements |
| [`fecef3c`](https://github.com/NoGod3524/EXReader/commit/fecef3c642112a4ed50d5841429578e77e0e6ef9) | 2026-10-18 | 0.18.0 | 3.19.1 | fix: skip zero-size copies when shaping an empty carry |
| [`072d131`](https://github.com/NoGod3524/EXReader/commit/072d1313a8d87b5458613b6b2a8b66a7ac5c9775) | 2026-10-18 | 0.18.0 | 3.19.1 | docs: record verified Unicode carry and empty shaping correction [skip ci] |
| [`4421413`](https://github.com/NoGod3524/EXReader/commit/4421413c8a4986cd43b0821dd64be4897007f011) | 2026-10-18 | 0.18.0 | 3.19.2 | fix: resolve displayed bidi and AUTO bases after spelling changes |
| [`3e332a6`](https://github.com/NoGod3524/EXReader/commit/3e332a6096666f3a7a96d4961a2e73a932876581) | 2026-10-18 | 0.18.0 | 3.19.2 | fix: exclude atomic ruby text from AUTO direction fast proof |
| [`93a4f27`](https://github.com/NoGod3524/EXReader/commit/93a4f271e315c627a3cf7be79b802fb648c2c703) | 2026-10-18 | 0.18.0 | 3.19.2 | docs: record verified display bidi and AUTO stress limits [skip ci] |
| [`dde7671`](https://github.com/NoGod3524/EXReader/commit/dde7671327a29ce14484ab84e897b2a2821266ea) | 2026-10-18 | 0.18.0 | 3.19.2 | fix: stabilize future bidi context before publishing pages |
| [`fb4e13c`](https://github.com/NoGod3524/EXReader/commit/fb4e13c753bdea12583cea75703688c5d0db1bb0) | 2026-10-18 | 0.18.0 | 3.19.2 | docs: record verified future bidi context and resource measurements [skip ci] |
| [`365f691`](https://github.com/NoGod3524/EXReader/commit/365f6916d32ee9c7c570e52124c48f36deea90b0) | 2026-10-18 | 0.18.0 | 3.19.3 | fix: wrap generated spelling by display graphemes |
| [`a08a7cd`](https://github.com/NoGod3524/EXReader/commit/a08a7cd0cd372dd402bc08f99630202e0a54eefd) | 2026-10-18 | 0.18.0 | 3.19.3 | docs: record verified generated spelling wrapping [skip ci] |
| [`f9754b0`](https://github.com/NoGod3524/EXReader/commit/f9754b05032f1b970d5ad75c111b91b7aadffab1) | 2026-10-18 | 0.18.0 | 3.20.0 | feat: preserve native dictionary spelling case with Unicode context |
| [`5f7a4ba`](https://github.com/NoGod3524/EXReader/commit/5f7a4ba32b581af5ac96cdeaa7173d2ca164d730) | 2026-10-18 | 0.18.0 | 3.20.0 | docs: record verified Unicode word-case SDK validation [skip ci] |
| [`177b6e1`](https://github.com/NoGod3524/EXReader/commit/177b6e1d6b7587612cde08340006bd2cd4adf21e) | 2026-10-18 | 0.18.0 | 3.20.1 | fix: reconstruct conditional compound stems with source-safe mapping |
| [`61e584a`](https://github.com/NoGod3524/EXReader/commit/61e584ae8bd7c13be97bb8a5459c185361899dbc) | 2026-10-18 | 0.18.0 | 3.20.1 | docs: record verified conditional compound SDK validation [skip ci] |
| [`840efcf`](https://github.com/NoGod3524/EXReader/commit/840efcfdcca2f7070453696a3e9c61a3580c3f5c) | 2026-10-18 | 0.18.0 | 3.21.0 | feat: paginate tall table groups with independent cell cursors |
| [`fb3f76b`](https://github.com/NoGod3524/EXReader/commit/fb3f76b13a95486994ab2198a59136294582bcc5) | 2026-10-18 | 0.18.0 | 3.21.0 | perf: probe tall table cells before retaining full layouts |
| [`4c78920`](https://github.com/NoGod3524/EXReader/commit/4c789208c3acb20e4fb5eb6ce97f75351474e8f0) | 2026-10-18 | 0.18.0 | 3.21.0 | docs: record verified tall table SDK and performance limits [skip ci] |
| [`4a994c0`](https://github.com/NoGod3524/EXReader/commit/4a994c040e26541a34df84f682d806b35a8798fe) | 2026-10-18 | 0.18.0 | 3.21.0 | perf: measure aligned table heights without full glyph retention |
| [`ef286bf`](https://github.com/NoGod3524/EXReader/commit/ef286bf31e3e05b51135bd65fbd0a86f37bf8f94) | 2026-10-18 | 0.18.0 | 3.21.0 | docs: record verified table alignment memory and SDK checks [skip ci] |
| [`b644e95`](https://github.com/NoGod3524/EXReader/commit/b644e95e89b54c0ee159fce0157f3b1cb469cc6b) | 2026-10-18 | 0.18.0 | 3.21.0 | perf: skip unneeded OpenType class filtering and verify platform fonts |
| [`79236e8`](https://github.com/NoGod3524/EXReader/commit/79236e84f8b80ec08dd656e1fd616e18bc52b111) | 2026-10-18 | 0.18.0 | 3.21.0 | docs: record verified OpenType filtering and platform font coverage [skip ci] |
| [`a1411af`](https://github.com/NoGod3524/EXReader/commit/a1411afc9547c61950ecb424049a8f7be43b0d11) | 2026-10-18 | 0.18.0 | 3.22.0 | feat: add native RGB blending and isolated PDF transparency groups |
| [`2fe46c6`](https://github.com/NoGod3524/EXReader/commit/2fe46c6c288c3691ca0bf4caedaac90f87300b68) | 2026-10-18 | 0.18.0 | 3.22.0 | docs: record verified PDF blending, SDK checks and rendering costs [skip ci] |
| [`ec8d4a9`](https://github.com/NoGod3524/EXReader/commit/ec8d4a98cdd6e63fa10a67e9a8521dfac743dd3e) | 2026-10-18 | 0.18.0 | 3.22.0 | feat: support non-isolated RGB PDF groups with independent references |
| [`381f5e7`](https://github.com/NoGod3524/EXReader/commit/381f5e7527ccecd31842de258fcf5c8337d8f0c5) | 2026-10-18 | 0.18.0 | 3.22.0 | docs: record verified non-isolated groups and complete project handoff [skip ci] |
| [`c58fce5`](https://github.com/NoGod3524/EXReader/commit/c58fce51f4a1bb2ada12dccd75d927543a40124a) | 2026-10-18 | 0.19.0 | 3.22.1 | chore: 0.19.0 housekeeping, parser fuzz driver and support matrix |
| [`c31311d`](https://github.com/NoGod3524/EXReader/commit/c31311d63d0f67585c9a16cf9e3eeda9d8ad9b4a) | 2026-10-18 | 0.19.0 | 3.22.1 | docs: add the knockout group reference and design (work package 1, step 1) |
| [`2228f59`](https://github.com/NoGod3524/EXReader/commit/2228f591aafaa72ce4ca9d4c24f54496f2aaa432) | 2026-10-18 | 0.19.0 | 3.22.1 | ci: build only the fuzz driver in the fuzz job |
| [`bbb18a7`](https://github.com/NoGod3524/EXReader/commit/bbb18a7f81ac5583b25af1018b0d2770a7377536) | 2026-10-18 | 0.19.0 | 3.22.1 | docs: record the 0.19.0 maintenance batch and seven-job CI [skip ci] |
| [`e8b5b7c`](https://github.com/NoGod3524/EXReader/commit/e8b5b7cf1be5618e899aec9c58713d54225f38cf) | 2026-10-18 | 0.19.0 | 3.23.0 | feat: render knockout transparency groups on the canvas and in PDF |
| [`6ced661`](https://github.com/NoGod3524/EXReader/commit/6ced661c2e15266d51ef4f8728a917c620d51ee9) | 2026-10-18 | 0.19.0 | 3.23.0 | docs: record the knockout implementation and seven-job CI [skip ci] |
| [`79c8d41`](https://github.com/NoGod3524/EXReader/commit/79c8d4180ff83bff0aef54840d73ddd065081637) | 2026-10-18 | 0.19.0 | 3.23.0 | test: add 42 knockout scenes with an independent Decimal reference |
| [`ac99751`](https://github.com/NoGod3524/EXReader/commit/ac997517bb9cab59ad4ddac2abc30ef92d26cff2) | 2026-10-18 | 0.19.0 | 3.23.0 | test: regress knockout budget, cancellation and legacy consumers |
| [`ceabedd`](https://github.com/NoGod3524/EXReader/commit/ceabedd23b81eb361ffda907ac8c8698835c275f) | 2026-10-18 | 0.19.0 | 3.23.0 | docs: record knockout scenes, regressions and seven-job CI [skip ci] |
| [`e057699`](https://github.com/NoGod3524/EXReader/commit/e0576992a587b0c718689e9fe9c844f527f2fef0) | 2026-10-18 | 0.19.0 | 3.23.0 | feat: composite nested groups against the knockout group's initial backdrop |
| [`060b7e0`](https://github.com/NoGod3524/EXReader/commit/060b7e05d1eda2adf5c1d0ca5cac7eb4f51d92a0) | 2026-10-18 | 0.19.0 | 3.23.0 | docs: record knockout nesting and alternating sampling [skip ci] |
| [`348d52b`](https://github.com/NoGod3524/EXReader/commit/348d52bb6c3545f1d214f2b4af79e1586c9a59ef) | 2026-10-18 | 0.19.0 | 3.23.0 | test: complete the knockout scene matrix |
| [`4da2746`](https://github.com/NoGod3524/EXReader/commit/4da27468522dda97f61401b113270b048d6906f6) | 2026-10-18 | 0.19.0 | 3.23.0 | docs: record work package 1 completion and seven-job CI [skip ci] |
| [`e37de3f`](https://github.com/NoGod3524/EXReader/commit/e37de3f63fa815fc0f73f56d71aab2e98d3df46c) | 2026-10-18 | 0.19.0 | 3.23.0 | docs: plan graphics-state soft masks for work package 2 [skip ci] |
| [`3a178bf`](https://github.com/NoGod3524/EXReader/commit/3a178bfe22fc2414ccca388e554cc6d80734d108) | 2026-10-18 | 0.19.0 | 3.24.0 | feat: add canvas and sink plumbing for graphics-state soft masks |
| [`e2d86b3`](https://github.com/NoGod3524/EXReader/commit/e2d86b3ace0eeaad13c1df4ff24d403b304528b0) | 2026-10-18 | 0.19.0 | 3.24.0 | feat: render graphics-state Alpha and Luminosity soft masks |
| [`0b08537`](https://github.com/NoGod3524/EXReader/commit/0b08537939ecf42a9fcfa37987cc2e7243987956) | 2026-10-18 | 0.19.0 | 3.24.0 | test: add the soft-mask scene matrix and rejection cases |
| [`4924d8c`](https://github.com/NoGod3524/EXReader/commit/4924d8c8f84e95132630f99548f9a98020aa1ebe) | 2026-10-18 | 0.19.0 | 3.24.0 | feat: exponential transfer functions and q/Q coverage for soft masks |
| [`c3504ab`](https://github.com/NoGod3524/EXReader/commit/c3504abc91a64655cd0efc88c1f8b33378f01ba4) | 2026-10-18 | 0.19.0 | 3.24.0 | docs: record the soft mask scenes and seven-job CI [skip ci] |
| [`bf1a646`](https://github.com/NoGod3524/EXReader/commit/bf1a64689d44852fefae8f5d3e648409724a4078) | 2026-10-18 | 0.19.0 | 3.24.0 | feat: finish soft-mask group semantics, colour-space validation and nesting |
| [`685961d`](https://github.com/NoGod3524/EXReader/commit/685961da63618ad1f93c951521d2d4878e9f75e4) | 2026-10-18 | 0.19.0 | 3.24.0 | docs: record soft-mask group, colour-space and nesting results [skip ci] |
| [`12fd6f9`](https://github.com/NoGod3524/EXReader/commit/12fd6f902d2f983ae15370bfc396f39a983fea81) | 2026-10-18 | 0.19.0 | 3.24.0 | docs: record the competitive goal and add a MuPDF comparison harness |
| [`85b4797`](https://github.com/NoGod3524/EXReader/commit/85b479716599374f426d46742f63286398718708) | 2026-10-18 | 0.19.0 | 3.24.1 | fix: treat soft masks as inherited paint state, as MuPDF does |
| [`993dbd3`](https://github.com/NoGod3524/EXReader/commit/993dbd301c8e12fad17b9d7e094f69f75192e94a) | 2026-10-18 | 0.19.0 | 3.24.1 | test: add a public PDF corpus fetcher and host-font support to the comparator |
| [`c6d6aaa`](https://github.com/NoGod3524/EXReader/commit/c6d6aaa054ebe060f4db46b95666b2ddd7364f24) | 2026-10-18 | 0.19.0 | 3.24.1 | docs: record the public corpus baseline and the top compatibility gaps |
| [`9227280`](https://github.com/NoGod3524/EXReader/commit/9227280e7455e64cfea8a37028f908fc1956179e) | 2026-10-18 | 0.19.0 | 3.24.1 | docs: plan work package 3 (group-area clipping) before touching the code |
| [`a3b7d2e`](https://github.com/NoGod3524/EXReader/commit/a3b7d2eefbaa9aa3b98be58b3f054065321455fa) | 2026-10-18 | 0.19.0 | 3.25.0 | refactor: index composite buffers through a working-buffer origin |
| [`e6ffe8b`](https://github.com/NoGod3524/EXReader/commit/e6ffe8b5e7010d1784bb170660cf3e2bdbce1899) | 2026-10-18 | 0.19.0 | 3.25.0 | docs: record the first group-region attempt and the annotation blocker |
| [`212c8e5`](https://github.com/NoGod3524/EXReader/commit/212c8e5c485c171ad45b85ffcf3f2aca0349b974) | 2026-10-18 | 0.19.0 | 3.25.0 | fix: report the device extent, not the active working buffer size |
| [`9fa6c4c`](https://github.com/NoGod3524/EXReader/commit/9fa6c4c9781528526cb0b81f4bcec4e03066db45) | 2026-10-18 | 0.19.0 | 3.25.0 | feat: region-sized working buffers for stateful transparency groups |
| [`8a415a8`](https://github.com/NoGod3524/EXReader/commit/8a415a8b10e9ff93fc51c9d48f26193cfd2b9fa0) | 2026-10-18 | 0.19.0 | 3.25.0 | merge: region-sized group working buffers |
| [`a9fbcc8`](https://github.com/NoGod3524/EXReader/commit/a9fbcc882d468bbc1629618cf1256893f9e5714a) | 2026-10-18 | 0.19.0 | 3.25.0 | fix: run the region setup before returning from begin_group |
| [`ad5b732`](https://github.com/NoGod3524/EXReader/commit/ad5b732131acbae69afc09c54ecb3020fe1b1d3d) | 2026-10-18 | 0.19.0 | 3.25.0 | feat: region buffers for isolated groups, and the WP3 acceptance data |
| [`5d94daa`](https://github.com/NoGod3524/EXReader/commit/5d94daa302fd8fa0351adb9c890b2cdcaa00c386) | 2026-10-18 | 0.19.0 | 3.25.0 | docs: freeze the PDF colour and image matrix for work package 4 |
| [`4382d04`](https://github.com/NoGod3524/EXReader/commit/4382d041f4046a12165d063965299da925e23f10) | 2026-10-18 | 0.19.0 | 3.26.0 | feat: honour the PDF rendering intent in ICC conversions |
| [`a12cba1`](https://github.com/NoGod3524/EXReader/commit/a12cba11087db78bbe7d7924d1a4d438871629f7) | 2026-10-18 | 0.19.0 | 3.26.0 | feat: accept four-component CMYK image mattes |
| [`58eba2d`](https://github.com/NoGod3524/EXReader/commit/58eba2dde6bb2c9f233a1ec34a69abb096626d85) | 2026-10-18 | 0.19.0 | 3.26.0 | feat: blend DeviceGray transparency groups in luminance |
| [`d66e1be`](https://github.com/NoGod3524/EXReader/commit/d66e1be4e4d9b1847753fe47ee54854a47854dd7) | 2026-10-18 | 0.19.0 | 3.26.0 | feat: honour the per-image rendering intent and fix the default |
| [`a8015dd`](https://github.com/NoGod3524/EXReader/commit/a8015dd2b4a06e111c7ddd2eb368047a998c483d) | 2026-10-18 | 0.19.0 | 3.26.0 | docs: record the OutputIntent investigation and defer it |
| [`58b2dd0`](https://github.com/NoGod3524/EXReader/commit/58b2dd0773400ed612a886f9a41e833a47aa0bb3) | 2026-10-18 | 0.19.0 | 3.26.1 | fix: report PDF shading as unsupported instead of malformed |
| [`5374ab7`](https://github.com/NoGod3524/EXReader/commit/5374ab78096fedc64d77875046f9729dd14d8aea) | 2026-10-18 | 0.19.0 | 3.26.1 | test: expect EXR_UNSUPPORTED for the sh operator |
| [`3db2b83`](https://github.com/NoGod3524/EXReader/commit/3db2b838f593fe5643d34fae180ff3b29e471354) | 2026-10-18 | 0.19.0 | 3.27.0 | wip: axial PDF shading (type 2) through a new sink entry — not merged |
| [`255bb34`](https://github.com/NoGod3524/EXReader/commit/255bb347acdab783367caea435870c05212e37aa) | 2026-10-18 | 0.19.0 | 3.27.0 | feat: render axial PDF shadings (type 2) |
| [`cffc2c1`](https://github.com/NoGod3524/EXReader/commit/cffc2c1d39ebc6b9a8ef891575f03b592e4e33b9) | 2026-10-18 | 0.19.0 | 3.27.0 | merge: axial PDF shadings |
| [`139c023`](https://github.com/NoGod3524/EXReader/commit/139c023431a21b694872335d23a5c8726968f677) | 2026-10-18 | 0.19.0 | 3.27.0 | feat: render radial PDF shadings (type 3) |
| [`d715fb9`](https://github.com/NoGod3524/EXReader/commit/d715fb9fb741cad03a05518a9f2abaafabb3b574) | 2026-10-19 | 0.19.0 | 3.28.0 | chore: roll back the corpus-compatibility work and keep only handoff items |
| [`dbb9d16`](https://github.com/NoGod3524/EXReader/commit/dbb9d160969271adec3e087bba7fe69d560c58f3) | 2026-10-19 | 0.19.0 | 3.28.0 | feat: paint dashed and dotted CSS borders |
| [`cbe4d3d`](https://github.com/NoGod3524/EXReader/commit/cbe4d3d3934cfb1274d77d488e628fbfb653e374) | 2026-10-19 | 0.19.0 | 3.28.0 | test: cover dotted table borders as well |
| [`360b081`](https://github.com/NoGod3524/EXReader/commit/360b081d0104670d928021d1443ca9dfb523b933) | 2026-10-19 | 0.19.0 | 3.28.0 | feat: render free-form and lattice mesh shadings (types 4 and 5) |
| [`db70495`](https://github.com/NoGod3524/EXReader/commit/db7049547407a7021504911512f815f7dee7b8e9) | 2026-10-19 | 0.19.0 | 3.28.0 | feat: take the CCITT row count from the image height when /Rows is absent |
| [`47a7ed1`](https://github.com/NoGod3524/EXReader/commit/47a7ed1222fd748b0c2da600c99036d4db6bd8a6) | 2026-10-19 | 0.19.0 | 3.28.0 | docs: record the work-package checkpoint and the open traps |
| [`ae811f7`](https://github.com/NoGod3524/EXReader/commit/ae811f796582c1e45274ffe8a82283cfd4bbe6e6) | 2026-10-19 | 0.19.0 | 3.28.0 | docs: record the table border line styles and percentage widths in the matrix [skip ci] |
| [`6a8992f`](https://github.com/NoGod3524/EXReader/commit/6a8992faee8f5e5d3babcc666eb490c384477acf) | 2026-10-19 | 0.19.0 | 3.28.1 | fix: continue type 4 mesh shadings from the correct shared edge on flag 2 |
| [`d43bac2`](https://github.com/NoGod3524/EXReader/commit/d43bac21604bbdc5d09123eaeec2a4e409d0a3d3) | 2026-10-19 | 0.19.0 | 3.28.1 | docs: note that the only type 7 samples are blocked upstream [skip ci] |
| [`50c0eeb`](https://github.com/NoGod3524/EXReader/commit/50c0eebcd9985665388ae21f2a47533de2aa282c) | 2026-10-19 | 0.19.0 | 3.29.0 | feat: accept object streams that extend another stream (/Extends) |
| [`04dda84`](https://github.com/NoGod3524/EXReader/commit/04dda8468c4626552375efc4f5f73fd4262469eb) | 2026-10-19 | 0.19.0 | 3.29.0 | docs: add the checkpoint audit for 50c0eeb [skip ci] |
| [`055c125`](https://github.com/NoGod3524/EXReader/commit/055c125d0292235c80f83002567f6b76ee49a0de) | 2026-10-19 | 0.19.0 | 3.29.0 | docs: record the dependency-ordered next steps [skip ci] |
| [`0f0f5ab`](https://github.com/NoGod3524/EXReader/commit/0f0f5abdd75604d7e230cd5d09f60c4c98bf082f) | 2026-10-19 | 0.19.0 | 3.29.0 | docs: record the default DeviceCMYK conversion difference [skip ci] |
| [`c8757d1`](https://github.com/NoGod3524/EXReader/commit/c8757d1a8108c7954f70a1f12b44245da5d11c18) | 2026-10-19 | 0.19.0 | 3.29.0 | docs: record the public-domain CMYK profile and the packaging options [skip ci] |
| [`49f30b9`](https://github.com/NoGod3524/EXReader/commit/49f30b925da9182dcf7dfa0d23dc362860e81c53) | 2026-10-19 | 0.19.0 | 3.29.0 | docs: record the post-rollback corpus baseline [skip ci] |
| [`8f3fbc8`](https://github.com/NoGod3524/EXReader/commit/8f3fbc865fd57f026fde691631e4836aac97e73d) | 2026-10-19 | 0.19.0 | 3.30.0 | feat: paint CSS double borders |
| [`bd0dfe7`](https://github.com/NoGod3524/EXReader/commit/bd0dfe737e3b39033919c3c0e3dc6d4e016fb08b) | 2026-10-19 | 0.19.0 | 3.30.0 | docs: add double to the border-style row [skip ci] |
| [`f4cee53`](https://github.com/NoGod3524/EXReader/commit/f4cee53f819f56fb4fa036331267e740c6358c62) | 2026-10-19 | 0.19.0 | 3.30.0 | test: cover the block (raster) path of double borders |
| [`444424c`](https://github.com/NoGod3524/EXReader/commit/444424c737bb59c5329e5bbe6885fcb97bfb7a79) | 2026-10-19 | 0.19.0 | 3.30.0 | docs: record that border-spacing is not implemented [skip ci] |
| [`aa59693`](https://github.com/NoGod3524/EXReader/commit/aa59693564358e84547443652fc6250aa3c0ff89) | 2026-10-19 | 0.19.0 | 3.30.0 | docs: hand off the current state to the next session [skip ci] |
| [`2a897d1`](https://github.com/NoGod3524/EXReader/commit/2a897d1637093acb8c4faf167fce4bdebc9a150e) | 2026-10-19 | 0.19.0 | 3.30.0 | feat: paint independent border sides and repeat table headers |
| [`db0ebae`](https://github.com/NoGod3524/EXReader/commit/db0ebae537970a85872ebca4df4cd33075a0ca59) | 2026-10-19 | 0.19.0 | 3.30.0 | docs: record the WP5 completion checkpoint [skip ci] |
| [`f0fd4b5`](https://github.com/NoGod3524/EXReader/commit/f0fd4b5209bc3108303adfef2ef449ba4552a04f) | 2026-10-19 | 0.19.0 | 3.31.0 | feat: render Coons and tensor mesh shadings and accept CMYK groups |
| [`cbf7804`](https://github.com/NoGod3524/EXReader/commit/cbf7804e2a9807352f910020e79ad9a0ea6cfe8d) | 2026-10-19 | 0.19.0 | 3.31.0 | docs: record the WP4 shading checkpoint [skip ci] |
| [`a959d79`](https://github.com/NoGod3524/EXReader/commit/a959d79143f537154466d8c0a0230dac90f99e4d) | 2026-10-19 | 0.19.0 | 3.31.0 | feat: blend DeviceCMYK transparency groups in a four-component canvas buffer |
| [`8feb927`](https://github.com/NoGod3524/EXReader/commit/8feb92716eb782dea35a4a25330097fda6db8c66) | 2026-10-19 | 0.19.0 | 3.31.0 | docs: record the canvas CMYK group checkpoint [skip ci] |
| [`1d24bf7`](https://github.com/NoGod3524/EXReader/commit/1d24bf79ee36acc2b171d65b46e495e3908d2b86) | 2026-10-19 | 0.19.0 | 3.31.0 | feat: feed PDF DeviceCMYK groups through the four-component buffer |
| [`f9a4491`](https://github.com/NoGod3524/EXReader/commit/f9a4491a966aa0ccfba86f61263582591b37c514) | 2026-10-19 | 0.19.0 | 3.31.0 | docs: record the end-to-end CMYK group checkpoint [skip ci] |
| [`8467141`](https://github.com/NoGod3524/EXReader/commit/846714194b2de8458beb774937c49fff7a183711) | 2026-10-19 | 0.19.0 | 3.31.0 | docs: 记录独立可读的后续开发交接 [skip ci] |
| [`ea38802`](https://github.com/NoGod3524/EXReader/commit/ea38802b3b2e53218b19a55612f885b81edc18f5) | 2026-10-19 | 0.19.0 | 3.32.0 | fix: correct rendering edge cases and adopt MIT licensing |
| [`2d49f1f`](https://github.com/NoGod3524/EXReader/commit/2d49f1ffbd5544f8ff7dc47c88ad452aee358d08) | 2026-10-19 | 0.19.0 | 3.32.0 | refactor: separate core responsibilities and check layer references |
| [`34a21ca`](https://github.com/NoGod3524/EXReader/commit/34a21ca7c47f07318af0a78fddb356caa2bf01c6) | 2026-10-19 | 0.19.0 | 3.32.0 | fix: link rendering test math dependencies explicitly |
| [`55089af`](https://github.com/NoGod3524/EXReader/commit/55089af988820c1b3ee68b9853f7f4dac907e757) | 2026-10-19 | 0.19.0 | 3.32.0 | fix: define LittleCMS fixed-point wrapping for GCC |
| [`127950e`](https://github.com/NoGod3524/EXReader/commit/127950e7a0592bbc0f100e06d92cea9234c26303) | 2026-10-19 | 0.19.0 | 3.32.0 | docs: record validated rendering and dependency checkpoint [skip ci] |
| [`716235e`](https://github.com/NoGod3524/EXReader/commit/716235e6ab4c5bb944c2e240b6a173289b3ab725) | 2026-10-19 | 0.19.0 | 3.33.0 | Split reading core and optional SDK components with dependency checks |
| [`ba9e13f`](https://github.com/NoGod3524/EXReader/commit/ba9e13fc870ad6f41046ffaccc21ce9a759e7690) | 2026-10-19 | 0.19.0 | 3.33.0 | Record validated component split and platform matrix [skip ci] |
| [`d3b2e51`](https://github.com/NoGod3524/EXReader/commit/d3b2e51092920d89fa71f10c623b6588c535c77e) | 2026-10-19 | 0.20.0 | 3.33.0 | Release modular SDK as 0.20.0 and clarify version increments |

## 旧编号对照

旧0.13–0.100实现步骤由上面的逐提交索引定位；S013–S100仍作为接口文档中的历史步骤标识。此前六个归并里程碑的范围对照如下。

| 此前归并编号 | 当时覆盖的原步骤 | 本次归属 |
| --- | --- | --- |
| 0.13 | S013–S018 | 2.5.0 |
| 0.14 | S019–S038 | 2.6.0、2.7.0及3.0.0的定位绘制模型 |
| 0.15 | S039–S071 | 3.0.0的PDF与固定页链路 |
| 0.16 | S072–S078 | 3.1.0 |
| 0.17 | S079–S090 | 3.2.0、3.3.0 |
| 0.18 | S091–S100 | 3.4.0、3.5.0 |

后续功能曾继续沿用0.18.0和0.19.0，对应后面的多个新批次，以提交索引为准。0.19.0长期复用于多个功能批次，不能整体对应一个新版本。此前分层版0.20.0（`d3b2e51`）对应本次**3.33.0**。

本次整理不新增引擎功能，也不重复增加版本；发布包、公开版本宏、组件版本与安装示例统一使用3.33.0。
