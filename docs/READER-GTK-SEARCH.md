# GTK 原生书内搜索

分支`codex/reader-gtk-search-ui`从固定`ce912f8c149e30cf3843e39258ae6889235495a0`接续。
冻结SDK与安装后的EXReaderSearch源码、产品schema、wire、共享模块和其它宿主保持不变。
源码`eb235427e6292413d624defadcce2e3c717032a5`的搜索专用诊断
[40119251223](https://github.com/NoGod3524/EXReader/actions/runs/40119251223)已通过30项实际UI与296项owner后端检查，
并保留安装Search的264项/34场景和F3的20组检查。同源完整保留回归
[40119936719](https://github.com/NoGod3524/EXReader/actions/runs/40119936719)已完成，搜索范围通过；
设置35项中的两项页色检查仍严格失败，因此整轮`failure, accepted=false`。
全部执行与工件处理仅在Actions。

可选`EXR_READER_GTK_SEARCH=ON`与`READER_SEARCH_PREFIX`接入已安装Search；默认构建不加入。
More末尾和Ctrl+Shift+F按需打开原生搜索面板，不增加常驻搜索栏。字面、区分大小写，1..4096个UTF-8字节，
每批32行，只保留当前批。结果行有独立索引、token和前后文；修改查询、取消、关闭、后台与换书不自动续扫。

搜索来源、模块句柄、批次selector和关闭都由现有SDK owner持有。UI只有复制的UTF-8安全标签及纯值路由索引。
句柄控制context地址固定；原fixed selector的显式长度保留在owner，不经C字符串往返。
搜索来源独立于当前阅读对象，使用当前字号、布局和已接受的设置。此为不支持跨打开恢复的临时搜索，不把SDK行号当全局身份。

明确选中真实结果行后，在当前阅读的独立公开SDK对象严格重新resolve，仅FOUND沿原帧接受/位置COMMIT路径导航。
EPUB保留spine index和part path；固定页按page ID找到实际页。歧义、缺失、无文字和失败没有偏移/页码兜底。
搜索、翻批、取消和关闭不改变当前阅读、SDK notes/progress或产品修订；只有明确FOUND导航允许改变阅读位置。

工作流`reader-gtk-search.yml`保留安装Search原264项/34场景、F3安装20项、原46+105+4+定向AT-SPI10及设置35项。
设置中的Light整页背景与Dark阅读页两项继续严格失败/pending，整体`accepted=false`；新增搜索范围独立报告。
新增探针包含真实250命中分页、Unicode、实际行选择、独立FOUND、重复spine、当前28字号、PDF/CBZ无文字、
实际模块control轮询中的取消、模态关闭/后台/换书/进程重开，以及数据库语义和原文件不变。

## 同源完整结果

受测源码`eb235427e6292413d624defadcce2e3c717032a5`，run`40119936719`，attempt1，job`120949078249`。

| 范围 | 实测结果 |
| --- | --- |
| 安装后的Search公开消费者 | 264项/34场景通过 |
| 安装后的F3设置包 | 20组通过 |
| 新GTK搜索owner后端 | 296项通过 |
| 新GTK实际搜索UI | 30/30通过 |
| 原账号/接收 | 46项通过 |
| 原阅读/产品/固定页/书架/metadata/collections UI | 20+5+24+14+15+27=105项通过 |
| 原故障/回归 | 4项通过 |
| 定向真实AT-SPI | 10项通过 |
| 原设置UI | 35项全部执行，33通过、2严格失败 |

两个失败保持原名：`light_foreground_and_background_change_page_pixels`与
`dark_theme_and_palette_change_page_pixels`。Light文字已有实际彩色墨迹，Light画布仍白色；
Dark/System只改变原生界面配色，阅读页继续保留可读的Light墨迹。本包不改冻结renderer或重染bitmap。

同源工件`12570897982`共41,990,425字节，SHA-256
`76b46b02588a543d27c6e18fe8c9a86fde036034c7855938b72b73e76502f9bb`，
有效期`2027-01-22T18:16:23Z`；上传日志与API digest一致。
实际程序SHA-256为`485a5bc611876cb543ef134f1dbef2e951023208bd531465b143446a7949228f`。
证据包含安装模块、build/link/provider记录、原始日志、Search逐项结果、帧截图、语义存储检查与保留回归。
此包授予GTK搜索的功能范围；性能、完整G13/Orca、整页主题与六平台互通仍分别验收。

## 原生选择器观察修复

实际GTK在Ctrl+L时先聚焦路径输入框，再提交内部location mode。同步焦点观察回调调用
`gtk_file_chooser_get_filename`会重入这个过渡，触发GTK的`check_save_entry`断言。
现在原生信号只安排一个合并idle；idle在过渡完成后读取选择路径和焦点，普通state输出只打印纯值缓存。
导入探针仍使用原30秒预算、真实输入框、一次粘贴与一次Return；不重放输入、不延长预算。

诊断实测TXT、EPUB、PDF、空PDF、CBZ和大章EPUB都完成实际原生选择器导入。
新UI的30项覆盖250行逐批真实结果、中文与emoji、歧义拒绝、独立FOUND、当前28字号、PDF实际第4页
（零起始page=3）、取消轮询、Escape、父窗口关闭、最小化、换书及进程重开；搜索只读期间当前帧像素、
SDK笔记/进度和产品修订语义不变。

## 保留的失败

| run | source | 原样失败与后续修正 |
| --- | --- | --- |
| 40113989871 | `edab920c` | 后端误将CBZ合法空文本当SDK拒绝；宿主显式拒绝无文字/OCR路径，模块保持不变。 |
| 40115156309 | `d5e83137` | 探针将selected字符数当布尔值；改为精确字符数，并对中文单独核对UTF-8字节范围。 |
| 40116175431 | `d480ca94` | 前16项UI已过，后续原生PDF选择器尚未形成有效路径；补实际焦点与路径观察。 |
| 40117108629 | `65d56195` | 新观察器同步重入原生选择器，引发GTK断言；保留该失败。 |
| 40117667176 | `9c404f18` | after焦点回调仍位于GTK过渡内，断言继续；云端只读诊断40118604990找到原始app日志。 |

只读诊断40118305747因旧工件没有failure-tree而失败；修正读取可选文件后，40118604990成功。
两次只读诊断均`diagnostic_only=true, accepted=false`，不授予产品范围。

具体受测source/run/attempt/job、原失败与工件身份见[验证记录](validation/reader-gtk-search.json)。
