# GTK 原生书内搜索

分支`codex/reader-gtk-search-ui`从固定`ce912f8c149e30cf3843e39258ae6889235495a0`接续。
冻结SDK与安装后的EXReaderSearch源码、产品schema、wire、共享模块和其它宿主保持不变。
本候选尚未编译或取得云端通过。全部执行与工件处理仅在Actions。

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

具体受测source/run/attempt/job、原失败与工件身份待云端运行后登记在[验证记录](validation/reader-gtk-search.json)。
