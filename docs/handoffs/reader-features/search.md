# F1：书内搜索

先读[共同约束](README.md)，从固定起点创建`codex/reader-search`。
目标是让四套原生壳共用可取消、有界返回、能精确导航的搜索结果。

## 文件归属

仅新增`apps/reader/search/**`、`tests/reader_search/**`、
`.github/workflows/reader-search.yml`、`docs/READER-SEARCH.md`、
`docs/validation/reader-search.json`。不要改reading-state、revisions或宿主。

## 交付契约

- 独立可选安装包`EXReaderSearch 0.1.0`，公开头`reader_search.h`。
  首版UTF-8字面量、区分大小写搜索；不做正则、OCR、TTS或持久化全文索引。
  空查询、非法UTF-8/NUL、查询超过4096字节明确拒绝。
- 三个显式来源：重排`exr_document`、有界EPUB publication/pager、固定页document。
  借用宿主owner上的句柄；函数、迭代句柄和关闭均按同一owner使用，拒绝重入。
  一次返回1..100个命中，带可继续的来源/位置游标；不得把整书命中保存在vector里。
- 重排复用公开find与anchor_create；固定页复用公开load_text/find/fixed_anchor_create，
  一次只保留当前页文本。EPUB按spine逐章，优先公开pager的流式文本接口，
  搜索状态跨32KiB块保留必要边界，不能拼整本/整章字符串当有界实现。
  sink回调内不能重入pager捕获锚点：先收集本批位置，退出SDK流式调用后再捕获。
- 命中保留完整路由：global chapter作用域、EPUB spine序号+原样part_path、
  fixed page_id+页提示、规范化UTF-8字节范围和公开捕获的exact/prefix/suffix。
  与固定起点reader_rs_encode_v2兼容；不插入修订、不保存笔记、不改变当前进度。
- 页码/偏移不作为失败后的兜底定位。返回结果在另一独立SDK实例上经公开resolve，
  FOUND才可导航；MISSING/AMBIGUOUS/LEGACY逐项保留状态。
- 明确命中是否重叠、游标推进、终止条件、所有字符串/结果释放接口。
  取消和SDK错误保留前一已成功批游标；失败批不当作完整结果。

## 云端出口

Windows/Linux安装后C与C++消费者；如声称macOS也须同源实际运行。
覆盖中文/emoji/UTF-8边界、块边界命中、重复文本、开头/结尾、无命中、空页、
多页PDF、跨章EPUB、重复spine路径、100项续页、取消/重试、错误/释放/owner。
验证搜索不改源文件、产品历史、SDK笔记及当前进度；旧v1/v2编码不改。
对固定规模长章记录实际峰值与扫描量，区分SDK自身和新增搜索内存；不据单次观测宣称性能达标。
工件保存输入清单、逐项结果、程序/安装文件身份与原始测量；只按实际平台授予。
