# SDK fuzz 驱动与可靠性计量

`tests/fuzz_parse.c` 是一个自带变异器的确定性 fuzz 驱动，不依赖 libFuzzer/AFL，也不需要额外运行时：
一个进程内用种子输入反复变异并直接调用内存解析入口。

## 覆盖的入口

| 输入判据 | 调用 |
| --- | --- |
| 种子扩展名 `.cbz` | `exr_fixed_open_memory(EXR_CBZ, ...)`，读取标题与页面头 |
| 种子扩展名 `.pdf`，或未知扩展名但以 `%PDF-` 开头 | `exr_fixed_open_memory(EXR_PDF, ...)`，读取标题与页数 |
| 种子扩展名 `.epub`，或未知扩展名但带 ZIP 头 `PK\x03\x04` | `exr_document_open_memory(EXR_EPUB, ...)`，读取标题/正文/章节/块 |
| 种子扩展名 `.fb2`，或未知扩展名但以 `<` 开头 | `exr_document_open_memory(EXR_FB2, ...)` |
| 其他 | `exr_document_open_memory(EXR_TXT, ...)` |

**格式跟随种子，而不是跟随变异后的头字节**：变异可能改掉 `%PDF-` 或 ZIP 头，若按头重新判型，
损坏样本会被送进错误的解析器。`.cbz` 与 `.epub` 都是 ZIP，必须由扩展名区分。

解析失败必须返回 `EXR_*` 状态而不是崩溃；驱动把「成功解析」与「干净拒绝」都视为通过。

## 运行

```sh
cmake -S . -B build/fuzz -DCMAKE_BUILD_TYPE=Debug -DEXR_SANITIZE=ON -DEXR_BUILD_FUZZ=ON
cmake --build build/fuzz --parallel 4
./build/fuzz/exreader-fuzz --seed 1 --iterations 200000 --save build/fuzz/last.bin \
  tests/fixtures/pdf-blend/nonisolated.pdf tests/fixtures/layout.epub \
  tests/fixtures/comic.cbz tests/fixtures/deep.fb2 tests/fixtures/sample.txt
```

参数：`--seed <n>`（默认 `0x9E3779B97F4A7C15`）、`--iterations <n>`（默认 10000）、
`--save <path>`（默认 `fuzz-last.bin`）、`--max-bytes <n>`（默认 1 MiB，固定变异工作区上限；
较大种子只复制其前缀，原种子仍完整读入内存）、`--cpu-seconds <n>`（正整数）。
指定 CPU 预算且没有显式迭代上限时持续运行至预算达到；同时指定时，任一上限达到就停。
输出 `process_cpu_seconds` 是本次循环的进程用户态与内核态 CPU 时间，包含变异和样本保存，
不等于墙钟耗时。单个输入卡死由外层进程超时判失败。
时钟、预算比较和证据汇总使用整数纳秒，文本保留九位小数；不将不足预算的时长四舍五入为达标。
CPU秒数最大为18446744073，超过整数纳秒范围会被拒绝。

种子状态为 `seed | 1`，所以相邻的偶数/奇数种子会重复同一序列；分片使用不同奇数。

复现单个输入：

```sh
./build/fuzz/exreader-fuzz --replay last.bin            # 读取 last.bin.format
./build/fuzz/exreader-fuzz --replay last.bin --format cbz
```

`--replay` 不做变异；默认读取样本旁的 `.format`（内容是解析器名），没有记录时才按扩展名/头判型。
`--format` 可显式覆盖，用于核对「同一字节交给哪个解析器」。

## 确定性与崩溃复现

- 变异序列只由 (seed, 语料顺序, 迭代次数) 决定，同一组合重复运行得到相同输入序列与相同 `parsed` 计数。
- 每次解析前把**即将解析的字节**写入 `--save` 文件，并把解析器名写入 `--save.format`；
  写入会 `flush` 并截断（Windows `_chsize_s`，POSIX `ftruncate`），所以较短的后续输入不会留下旧尾部。
  崩溃或卡住后，`last.bin` 与 `last.bin.format` 就是精确的触发样本与解析器。
- 正常结束打印 `fuzz: N iterations over M seeds, K reached a parsed document, no crash`，
  并按格式打印 `format=<name> attempts=<n> parsed=<n>`。

## CBZ 成员解压的有界实现

`src/cbz.c` 不用 miniz 的 `mz_zip_reader_extract_iter_*`：central directory 只当索引，
**本地文件头才是成员数据的权威尺寸**。变异可以把 central 的 `compressed size` 改小，
让 miniz 在压缩流中途耗尽输入并陷入不前进的迭代循环；`tinfl_decompress` 的
`FAILED_CANNOT_MAKE_PROGRESS` 也可能在输出恰好填满时出现。

因此成员读取按本地文件头取数据偏移与尺寸（data descriptor 场景回退到 central），
用 `tinfl_decompress` 的 `TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF` 自行循环，并保证：

- 每轮必须消耗输入或产出输出，否则以 `EXR_FORMAT` 结束；
- 输出达到上限（头 1 MiB / 成员 32 MiB）即停；
- 完整成员校验 CRC，尺寸不符或 CRC 不符都返回明确错误。

回归样本 `tests/fixtures/fuzz-cbz-truncated.bin`（908 字节，SHA-256
`449011aa8cdd09984120b894e94309570113d7d6f7ccbbced27792824f9f48a7`）在旧驱动上会卡住，
现在由 `native-fuzz-driver` 断言以 `EXR_FORMAT` 结束。

## 字体、分页与绘制入口

同一变异/保存/重放循环编译为三个独立程序，不增加 SDK 公共接口：

| 程序 | 实际执行 | `.format` |
| --- | --- | --- |
| `exreader-fuzz-font` | TTF/OTF/TTC 第0 face；查询可变轴；混合文字横排LTR/RTL与竖排塑形、轮廓、位图、COLRv0图层 | `font` |
| `exreader-fuzz-layout` | 解析重排文档、创建 pager、最多前4页；检查源范围与有限坐标 | `layout:txt`、`layout:epub` 等 |
| `exreader-fuzz-render` | 重排页及 PDF/CBZ 最多前4页的灰度与RGBA绘制 | `render:pdf`、`render:cbz` 等 |

layout/render 必须给出 `--font <宿主字体>`。重排视口192×256，固定页按 unit scale
缩至不超过256像素；每次 exercise 最多4096次取消轮询。超限/取消可干净拒绝，
不代表完整文档绘制成功。可变字体目前查询轴，不构造轴极值实例；TTC 不遍历所有 face。
当前没有 WOFF 专用种子或解码覆盖。字体计划包含 COLRv1、可变 COLRv1 和 SVG 字体种子，
执行颜色信息查询及有界页绘制。EPUB 按输入长度奇偶分流到快照或有界章阅读，两条路径共享原单次工作上限。

```sh
./build/fuzz/exreader-fuzz-font --seed 1 --iterations 20000 --save build/fuzz/font.bin tests/fixtures/fonts/primary.ttf tests/fixtures/fonts/variable.ttf
./build/fuzz/exreader-fuzz-layout --font tests/fixtures/fonts/primary.ttf --seed 1 --iterations 2000 --save build/fuzz/layout.bin tests/fixtures/layout.epub
./build/fuzz/exreader-fuzz-render --font tests/fixtures/fonts/primary.ttf --replay build/fuzz/render.bin
```

重放必须使用对应程序，错误目标会拒绝 `.format`。`tests/check_fuzz_pipelines.py`
检查有效输入可达、精确记录、确定性、跨目标拒绝与实际 CPU 预算。

## CI 与长跑

`.github/workflows/native.yml` 的 `fuzz` 作业用 ASan/UBSan 构建并在每次推送跑 20 万次迭代（约数分钟）；
失败时保留并上传 `last.bin` 与 `last.bin.format`。同一 sanitizer 构建还会执行
`exreader-fuzz-test`（驱动回归：短输入截断、只读写入失败、CBZ 实际解析、扩展名/损坏头路由、
数字参数拒绝、卡住样本的明确错误），失败时样本与格式记录随 artifact 一并保留。
Ctest 另有 `native-fuzz-smoke`（500次）、三个 pipeline smoke、pipeline contract
和纯合成的 accounting 回归；合成汇总数据不属于真实长测结果。CI 同时执行三个 pipeline 的短测。

发布验收目标是每个目标持续 ≥24 CPU 小时。记录工具固定各目标语料，保存源码SHA、
语料/字体/程序/运行库散列、进程CPU与墙钟时间、退出结果、日志和最后输入：

```sh
python3 tools/run_reliability_campaign.py seal-build --source . --build build/fuzz --require-clean
python3 tools/run_reliability_campaign.py run --source . --build build/fuzz --target font \
  --seed 2026101901 --cpu-seconds 3600 --require-clean --output build/evidence/font-0
python3 tools/run_reliability_campaign.py summarize --reports build/evidence \
  --minimum-cpu-hours 24 --expected-shards 24 --first-seed 2026101901 \
  --build-manifest build/fuzz/build-manifest.json --output build/reliability-summary.json
```

`--target` 支持 parser/font/layout/render。输出目录必须为空，Windows 源码/构建/输出路径
需选用 ASCII 路径或 junction，以兼容驱动的窄字符文件入口。
汇总要求四个目标齐全、同一提交、干净且开启sanitizer、输入/二进制不变、每目标同一语料与构建、
有效种子不重复、全部分片成功且CPU足额；失败或缺失分片不能换算成通过时长。
schema3要求每片同时保存`report.json`、`run.log`、`last.bin`、`last.bin.format`和
`build-manifest.json`。汇总逐项核对散列、原始日志计量、目标标签、语料顺序与数量、
计数范围和字段类型，拒绝缺字段、重复JSON键、非有限数字、布尔值冒充数字和旧schema。
layout/render 每片还须记录 `bounded_chapter_attempts` 和 `bounded_chapter_completed`，
完成数仅计返回成功且实际生成页面的有界章操作；两项都须非零，并与原始日志、总尝试数和总成功数一致。
快照路径的成功不能代替有界章路径的成功。
构建清单包含四个程序、SDK运行库和CMakeCache的散列；Linux验收还检查各程序及运行库的
ASan/UBSan导入符号。运行时固定sanitizer失败即停，并记录实际使用的选项。
清单只生成一次；运行前后核对构建与输入，汇总对照独立下载的构建清单。
成功汇总包含每份原始报告的路径和散列，已有汇总或非空运行目录都不会覆盖。

手动工作流 `.github/workflows/reliability.yml` 复用一份 Ubuntu ASan/UBSan 构建，
四目标各24分片，每片1进程CPU小时，最多8片并行；无论成功失败均尝试上传报告与最后输入。
工作流先验证归档重定位后的四目标可加载；各分片保留独立artifact目录，汇总校验准确分片数、
种子计划和本次源码SHA，并要求构建及全部分片作业成功。
手动输入`smoke=true`仅运行四个1秒分片以验证工作流；默认`false`执行24CPU小时验收。
常规CI也生成四目标1秒证据及短测汇总，始终上传已产生的证据。
只有汇总通过后才能记为每目标24CPU小时；短测与迭代次数不能替代。

## 尚未覆盖

- 更多字体face、可变轴实例、WOFF与更多文字输入；
- 第4页之后的状态、随机续排和更大视口的变异测试；
- 结构化语料裁剪（目前只做字节级变异，没有按 PDF 对象/ZIP 成员切分）。
以上随工作包 16 扩展，扩展时保持同一条「先落盘再解析」的复现规则。
