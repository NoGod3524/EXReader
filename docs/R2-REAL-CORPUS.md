# R2 真实阅读语料

共同起点为 `9bd2b2c3caf1f63dc4437e0af978247494e87145`；原SDK为`9c69bc4…`，当前SDK冻结为`9854061…`。
本批八份出版物由源站提供，原始字节不修改，不与合成夹具混计。
当前结果：源码`da1c183…`、run39899523839同次full8/8、location8/8严格通过，完整身份见文末。

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

2026-10-31，Gutenberg 的 pg84 和 pg1342 在线 EPUB 字节发生变化。原件已从通过验收的
run `39974986212` 恢复并保存于 `tools/reading_corpus/frozen/`；恢复来源、工件 ZIP 散列及
两份原件身份见该目录的 README。采集仍校验登记 SHA-256、长度、字节上限和当前许可条款，
并记录实际读取的固定文件 URI；发现模式继续访问源站。冻结清单、参考页、预期结果和预算不变。

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
首轮真实执行源码为 `232a1806c38e0775892da2b4dd82fe6cd90414b2`，run `39888135957`：

| 原件 | 完整遍历 | 独立重开定位 | 结论 |
| --- | --- | --- | --- |
| Alice | 226页、16/16部分 | 15文字部分+1空文字部分 | 通过 |
| Frankenstein | 539页、33/33部分 | 32文字部分+1空文字部分 | 通过 |
| Pride | 97页、1/10部分后资源限制 | 9文字部分+1空文字部分 | 未通过：64 MiB解码图像缓存 |
| Moby Dick | 1449页、14/14部分 | 13文字部分+1空文字部分 | 通过 |
| W-9 | 6/6页 | 6/6页 | 通过 |
| NIST AI RMF | 16页后资源限制 | 48/48页 | 未通过：PDF解码流缓存预算 |
| NIST CSF2 | 首面绘制格式拒绝 | 首面文字格式拒绝 | 未通过：ToUnicode codespace/mapping |
| NASA图册 | 首面绘制格式拒绝 | 首面文字格式拒绝 | 未通过：ToUnicode codespace/mapping |

严格结果 `accepted=false`，完整遍历4通过/4失败、定位6通过/2失败；没有超时。
20项协议检查通过，但不替代真实文档验收。
工件 `r2-real-corpus-39888135957-1` ID `12473113944`，40,674,221字节，
SHA-256 `5560d15611a4ca27e189efb9ad94a0257caebbe4f086dd362aff7609842719a2`。
原件位于 `inputs/assets/`，完整逐项原件证据位于 `evidence/full/`，定位位于 `evidence/location/`。

诊断run `39888572521` 从云端恢复原工件及原二进制、核对散列并重放四个失败，
复用 `tools/triage_corpus.py` 与 `tools/check_pdf_reference.py`。PyMuPDF 1.26.7对四份均完整绘制与提取，
未作参考修复、无需密码；PDF参考分别完成48/32/42页。Pride参考完成473个参考分页，
不同分页配置的参考页数不与本引擎页数作相等断言。
诊断只分类为两个资源限制、两个参考完成但主引擎拒绝，`accepted=false`；不授予保真结论。
图像缓存修复由本包负责，PDF流缓存由集成负责人负责，ToUnicode由R4负责；避免并改同一引擎文件。
之后仍须原八份、原预期、同一新源码完整重跑，不能拼接旧通过项。

## 图像缓存候选

候选 `9114b24228c856327de30e045f4ed017b3f39251` 保留64 MiB解码图像上限。
顶层分页操作开始时，只有没有任何独立页面引用的旧图像才被标为可逐出；
本次操作命中后即取消标记。新图像造成预算压力时才逐出仍然无引用的已标记项。
不能在页面中途仅凭引用计数逐出：图片box在`seal()`前尚未取得引用。
未完成局部流、浮动、表格片段与调用者保留的页面继续持有原像素，历史小图缓存继续复用。

`native-page-cache`新增八份16 MiB图像的跨页压力回归、旧页保活与倒翻、
取消后页面可绘制、同页超限拒绝、整文档布局超限拒绝。固定旧SDK运行同一新增回归必须失败，
并保留原64 MiB拒绝原因；既有小图只解码一次断言保留。
run `39890510578`的完整native Release 168/168、ASan/UBSan 165/165通过。
首次旧SDK拒绝控制因浅克隆无法找到登记基线而失败；保留该失败。
`d67a68e09ea18396c5bc84b9d0b93ff45ef43823`只将checkout改为完整历史，
重跑run `39890990240`的Release再次168/168通过，旧SDK控制明确检出64 MiB累计图像拒绝；
ASan/UBSan也完成165/165，`native-page-cache`在两种构建均通过。
Release工件ID `12474148828`、14,180字节、
SHA-256 `a55ce7bc59047372002fe957ef05fefb59acb0210d0091873274a113af581071`。
sanitizer工件ID `12475500911`、13,613字节、
SHA-256 `484583fdc95b9bd79a8204927aa5fb37e3688ce54fd7921a5a56c32bc62331e3`。

原八份真实文档run `39890510535`在候选`9114b24`完成：Pride由97页限制修至963页、10/10部分完整通过；
其余四份先前通过项仍通过，三个PDF仍保留原失败。完整遍历5通过/3失败、定位6通过/2失败，
严格`accepted=false`。工件ID `12474901013`，
SHA-256 `ff826618e1764bb07ed733c82e9c60133dba2eda95e388831cdbf1a0fb7f7e3c`。

## 组合候选完整重跑

`c358df7bdc128a478c3a2d21a68d2bff89d06632`合入图像缓存、PDF解码流操作边界、
公共固定页面选项回归修正和R4单字节ToUnicode映射修复。
原八份、原预期、同一manifest与登记提交的完整重跑为run `39891591170`。
manifest SHA-256仍为`f71f8a24faff664a03b7e15a7f424ec354f83c53fbd14f602d4b050f3fd19de1`。

| 原件 | 完整遍历 | 独立重开定位 | 结论 |
| --- | --- | --- | --- |
| Alice | 226页、16/16部分 | 15文字部分+1空文字部分 | 通过 |
| Frankenstein | 539页、33/33部分 | 32文字部分+1空文字部分 | 通过 |
| Pride | 963页、10/10部分 | 9文字部分+1空文字部分 | 通过 |
| Moby Dick | 1449页、14/14部分 | 13文字部分+1空文字部分 | 通过 |
| W-9 | 6/6页、37,688文字字节 | 6/6页 | 通过 |
| NIST AI RMF | 48/48页、91,074文字字节 | 48/48页 | 通过 |
| NIST CSF2 | 32/32页、68,794文字字节 | 32/32页 | 通过 |
| NASA图册 | 首面绘制`status=11`，完成0页 | 42/42页 | 未通过，保留成功预期 |

完整遍历7通过/1失败，定位8通过，严格`accepted=false`。
工件`r2-real-corpus-39891591170-1` ID `12475246637`、40,675,156字节、
SHA-256 `dc1dfa45cbb6aa3b4ac61f08a3bf2c4e6e5c7c4db81a8f3f6e9b2aedeb31c844`。
NASA后续由R4继续诊断绘制；不将此状态改为预期拒绝，不拼接其他源码旧通过项。

## PDF解码流生命周期独立源码复核

对组合候选中的`pdf_objects.c`与`pdf_document.c`五个清理入口作只读复核，未发现越过操作边界的借用：

| 路径 | 清理前完成的持有者 | 依据 |
| --- | --- | --- |
| 页面绘制、AP、嵌套Form和Type3 | 同步递归解释器先关闭font/colorspace，painter再关闭FreeType face、ICC与软蒙版 | `pdf_document.c:41`、`pdf_content.c:416`、`pdf_content.c:651`、`pdf_paint.c:201`、`pdf_annotation_paint.c:225` |
| 字体程序、CIDToGID、颜色空间与函数 | font程序和CID表借解码流；其font/face都先关闭。Indexed颜色表和采样函数复制源数据；calculator/ICC在所属颜色空间销毁时结束 | `pdf_font.c:238`、`pdf_font.c:269`、`pdf_color.c:156`、`pdf_function.c:120` |
| 文字、元数据、注释和位图返回值 | 文字及regions复制；Info/XMP与annotation字段单独分配；公开fixed层再次复制metadata/annotation；canvas输出独立像素 | `fixed_text.c:31`、`pdf_document.c:110`、`pdf_annotations.c:42`、`fixed.c:91`、`pdf_raster.c:40` |
| 页面目录及对象流索引 | 页面只保留对象ID与数值；对象流objects/offsets独立分配，解析字符串进入file拥有的strings | `pdf_pages.c:105`、`pdf_objects.c:413`、`pdf_objects.c:727` |
| 工作预算与重入 | 仅成功顶层出口清零work/decode_work，失败销毁reader；嵌套Form/Type3/AP无清零入口。fixed层busy拒绝同文档重入 | `pdf_objects.c:727`、`pdf_document.c:52`、`fixed.c:95`、`fixed.c:163` |

64 MiB单流、128 MiB单操作累计和256 MiB解码工作预算继续在操作内部执行；
跨已结束操作不再累计。上述为源码生命周期复核，云端回归及真实原件结果分别保留于对应run。

## 保留结果与运行身份

`933136f1a0394d3e141c9edea0e0ff0182dc4a80`与`d0d49a3fa1e3961f3ed9bfb8567e35196c0f4c99`
补上许可、平台拒绝回归以及R2逐项结果的source/run/attempt身份。
平台拒绝回归还绑定其原`platform-evidence.json`的SHA-256，并在重放前拒绝旧运行身份。
`validate_evidence(report,evidence_root)`按固定相对路径重新读取八份整本与定位结果、
核结果及原生stdout/stderr散列、分类、退出值、原件散列、实际报告和逐定位unit；
成功报告还绑定完整遍历summary散列。发布聚合器应传入工件的`evidence/`目录调用此接口。

所有执行留在Actions，新增检查不授予真实文档信用：

| 云端run | 源码 | 结果 |
| --- | --- | --- |
| `39893109469` | `d0d49a3` | 原20项加23项证据正反例，共43项协议检查通过；完整原八份仍7通过/1个NASA绘制拒绝，定位8通过，`accepted=false` |
| `39892985589` | `933136f` | 两个profile许可材料均通过；每个保留31项负例、1项缺强制材料检查和3项源材料正例；日志含实际CI身份 |
| `39892988022` | `933136f` | Windows/macOS四个profile均通过；core拒绝回归各25/25、library各30/30 |

最终协议run的原八份工件ID `12476130205`、40,676,049字节、
SHA-256 `f3316fe9d4bddb4a8d0f73e695cc63f01973000f2345965987d8ba1c54a914d9`。
旧失败工件不变；NASA修复后仍须同八份、同预期完整重跑。

## JPX组合源码八份完整验收

源码`9854061be331fe603a1822d9b2b36ee357154927`的run `39897525130`、attempt `1`、
普通JPX ON job `120231287075`实际构建SDK，执行`native-pdf-jpx`及其余原生测试4/4，
通过分层检查，安装私有`libexr_vendor_exr_jpx.a`，再从安装产物构建整本与定位消费者。
运行只从旧工件`12474886324`恢复原件输入；旧结果不计入本次验收。

登记仍为`ea5c13e081cfba86d9f6dd759439894463e51126`，manifest SHA-256仍为
`f71f8a24faff664a03b7e15a7f424ec354f83c53fbd14f602d4b050f3fd19de1`。
43项协议检查通过后，八份原件保持`status=0, complete=true`原预期，各自重新运行整本及独立定位：

| 原件 | 完整遍历 | 独立重开定位 | 结论 |
| --- | --- | --- | --- |
| Alice | 226页、16/16部分 | 15文字部分+1空文字部分 | 通过 |
| Frankenstein | 539页、33/33部分 | 32文字部分+1空文字部分 | 通过 |
| Pride | 963页、10/10部分 | 9文字部分+1空文字部分 | 通过 |
| Moby Dick | 1449页、14/14部分 | 13文字部分+1空文字部分 | 通过 |
| W-9 | 6/6页、37,688文字字节 | 6/6页 | 通过 |
| NIST AI RMF | 48/48页、91,074文字字节 | 48/48页 | 通过 |
| NIST CSF2 | 32/32页、68,794文字字节 | 32/32页 | 通过 |
| NASA图册 | 42/42页、144,089文字字节 | 42/42页 | 通过 |

完整遍历8/8、定位8/8，`validate_evidence`重核16份结果及原生stdout/stderr后，
本次代表性八份报告`accepted=true`。所有结果绑定上述同一source/run/attempt；
NASA整本结果SHA-256为`062e851851d9d37a25a9a74189c8b582d0862ed861c235108447727710e2adce`，
定位结果SHA-256为`544b083e65255814e240857f22b58c62a1721b86eb41f15fbdc9b0dacadac1ee`。

本次工件`r6-jpx-ON-OFF-39897525130-1` ID `12477093996`、34,096,491字节、
SHA-256 `567df1f70bf3561a854eaeb3b26e2b70ff03b773321debf33d3227803363d35e`。
原件位于`jpx-retained/real-inputs/assets/`，新结果及原始证据位于`jpx-real-evidence/`。

同一job的公开JPX像素对照仍失败：11个成功图像均通过本引擎与已知源像素精确比较，
但Poppler对照像素不同；另有embedded-alpha拒绝状态与冻结计划不同。
job整体保持失败，八份语料通过不授予该JPX门禁通过。历史1710目标与其他未覆盖项仍按前述范围保留。

## 最终JPX与原八份同次通过

后继源码`da1c1833d89932612d8e4549fee5aec378555ad4`、[run39899523839](https://github.com/NoGod3524/EXReader/actions/runs/39899523839)、
attempt1的三个作业全部success。普通ON job120237609130重新执行相同原八份，
full8/8、location8/8，逐项原始证据严格重核后accepted=true；登记与manifest SHA未改。
该job的24项JPX公开SDK专项同次通过；ASan/UBSan与JPX关闭作业的各24项也全部通过。
没有拼接run39897525130或其他旧结果，旧失败继续保留。

原八份及本次新证据位于工件`r6-jpx-ON-OFF-39899523839-1`，
ID12478720699、34,100,503字节、SHA-256`756edd9f4e86f365f2d0010f5aeea25efcfd5e481e13715c0b7b05df2054e976`。
三份工件完整元数据与声明见[最终JPX记录](validation/reading-jpx-final-da1c183.json)。
本次授予固定八份代表语料及JPX声明范围通过，历史1710库存、正式性能与发布仍分别验收。
