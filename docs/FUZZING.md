# 解析器 fuzz 驱动

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

参数：`--seed <n>`（默认 1）、`--iterations <n>`、`--save <path>`（默认 `fuzz-last.bin`）、
`--max-bytes <n>`（默认 1 MiB，超过语料最大尺寸时自动放大）。

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

## CI 与长跑

`.github/workflows/native.yml` 的 `fuzz` 作业用 ASan/UBSan 构建并在每次推送跑 20 万次迭代（约数分钟）；
失败时保留并上传 `last.bin` 与 `last.bin.format`。同一 sanitizer 构建还会执行
`exreader-fuzz-test`（驱动回归：短输入截断、只读写入失败、CBZ 实际解析、扩展名/损坏头路由、
数字参数拒绝、卡住样本的明确错误），失败时样本与格式记录随 artifact 一并保留。
Ctest 另有 `native-fuzz-smoke`（500 次迭代）保证驱动本身可用。

发布验收目标是每个目标持续 ≥24 CPU 小时：

```sh
./build/fuzz/exreader-fuzz --seed 20261018 --iterations 2000000000 --save /tmp/last.bin <种子...>
```

## 尚未覆盖

- 字体文件（TTF/OTF/WOFF）与布局/分页入口；
- CBZ 的整页图像解码/绘制路径（当前只读取页面头与元数据）；
- 结构化语料裁剪（目前只做字节级变异，没有按 PDF 对象/ZIP 成员切分）。
以上随工作包 16 扩展，扩展时保持同一条「先落盘再解析」的复现规则。
