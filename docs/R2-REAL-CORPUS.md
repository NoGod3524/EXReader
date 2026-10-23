# R2 真实阅读语料

共同起点为 `9bd2b2c3caf1f63dc4437e0af978247494e87145`，SDK 保护树为 `9c69bc4c7efb0cff68ced27562709fe597189041`。
本批八份出版物由源站提供，原始字节不修改，不与合成夹具混计。

## 冻结清单与来源

唯一清单是 `tools/reading_corpus/real-v1.json`，R2/R3 共用。候选先于引擎运行登记于
`04daea48a8db0734a0c4c81ee9a4e1dd185e4a81`，云端仅收集运行 `39887277694`
在 `5c379a5720d153a51b31143240c4488f57cf1e49` 取回全部八份并输出每文件散列、字节与结构；没有运行 SDK。
初次收集 `39887038416` 的两个错误保留：Pride 图版超过 16 MiB 下载界、NASA 原链接 404。
第二次仅在引擎执行前将 Pride 下载界定为 64 MiB，并从 NASA 官方目录更正同一出版物链接。
八份原成功期望全部保持 `status=0, complete=true`。不能按结果删文件或改成预期拒绝。

| 覆盖 | 冻结出版物 | 已独立观测结构 | 出口及缺项 |
| --- | --- | --- | --- |
| 多章真实 EPUB | PG11、PG84、PG1342、PG2701 | 15/32/9/13 个 spine 项 | 所有部分分页绘制、文字及重开选择器；spine 项不等于作者章数 |
| 长散文与图像 EPUB | Frankenstein、Pride、Moby Dick | 最大压缩包成员约 253–256 KiB；Pride 有164图、23.7 MiB归档 | 不替代50 MiB合成长章压力验收；最大成员未预先冒充纯文本章长 |
| 常见多页 PDF、字体、表格 | W-9、NIST AI RMF、NIST CSF2 | 6/48/32页；PDF1.6/1.7；pdfTeX与Adobe生成器 | 全页绘制/文字及重开定位；不执行JavaScript/XFA交互，不验表单写回 |
| 图像型 PDF | NASA太阳系图册2013 | 42页、4.9 MiB、Adobe InDesign | 保留图像与页上文字；图像页无文字按空文字单列 |
| 历史 EPUB11超时、5限制、1参数状态 | 原件未恢复 | 只有历史本地报告路径及汇总 | 继续待恢复，不能以本批替代 |
| 历史 PDF54参考完成但拒绝、8参考修复、4待审、7不支持 | 原件未恢复 | 只有历史汇总 | 继续待恢复，不能把本批失败自动归为旧同一缺陷 |
| 加密、损坏修复、亚洲/RTL多脚本字体、扫描OCR | 本批未覆盖 | 无 | 后续按覆盖缺口新增独立清单，保留本批全部结果 |

`selected_pages` 是 R3 测量采样，不能限制 R2 整本执行；EPUB页号依赖分页，R3记录实际 part/page。
R2每文件墙钟120秒、独立进程；定位再独立进程120秒。超时、实际拒绝、进程异常与预期不符分别报告。

## 许可审查

PG四份的官方RDF和包内`dc:rights`均声明美国公版，原书Gutenberg条款与作者/插图署名完整保留。
本批在US runner上读取未经改动出版物，不宣称全球公版。依据为各文件官方RDF及原EPUB，不以仓库许可证替代内容权利。

IRS W-9是官方税务表格，源站[内容使用政策](https://www.irs.gov/about-irs/use-of-content-from-irsgov)
允许复制联邦雇员职务内容，要求署名且不造成背书。本批保留整份官方表格。
NIST两份均是官方Technical Series出版物；[NIST政策](https://www.nist.gov/open/license)
说明雇员作品、技术出版物复用及署名要求，文档原有引用和声明不变。
NASA图册来自[官方教育目录](https://www.nasa.gov/stem-content/our-solar-system-lithograph-set/)，
按[NASA媒体政策](https://www.nasa.gov/nasa-brand-center/images-and-media/)用于事实性阅读与渲染研究，保留原图像署名，
不将NASA徽标用作项目标识或宣传。相关NASA/JPL-Caltech图像依据[JPL政策](https://www.jpl.nasa.gov/jpl-image-use-policy/)保留署名。
本批不为第三方图片另授商业宣传或商品化使用权。

清单逐项固定来源、原件SHA-256/长度、许可URL与首次云端原文快照SHA-256。
HTML许可页含动态内容，同一政策逐请求原始散列可不同；执行时保留新原文与新散列，核必要许可条款，
不把动态HTML当作原始书籍身份。初次原文仍由收集run工件保留，文档SHA和字节必须逐次完全相同。

## 执行接口

在Actions runner执行：

```sh
python3 tools/reading_corpus/collect.py collect tools/reading_corpus/real-v1.json build/r2-inputs
```

输入位于 `build/r2-inputs/assets/<manifest path>`；输出目录必须不存在。
收集器不会运行SDK、挑选通过文件或更改原预期。清单第一次加入Git的提交是运行登记锚点。
R2严格入口稳定check名称为 `R2 real document acceptance`，报告绑定source/run/attempt/manifest/font/binaries。

## 当前范围

旧1710政策目标仍保留，历史已通过真实语料仍0/1710；本批是独立八份入口。
当前仅收集已完成，打开/绘制/文字/定位结果等待固定清单后的首次云端执行。
