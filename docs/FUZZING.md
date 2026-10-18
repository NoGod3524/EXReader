# 解析器 fuzz 驱动

`tests/fuzz_parse.c` 是一个自带变异器的确定性 fuzz 驱动，不依赖 libFuzzer/AFL，也不需要额外运行时：
一个进程内用种子输入反复变异并直接调用内存解析入口。

## 覆盖的入口

| 输入判据 | 调用 |
| --- | --- |
| 以 `%PDF-` 开头 | `exr_fixed_open_memory(EXR_PDF, ...)`，读取标题与页数 |
| ZIP 头 `PK\x03\x04` | `exr_document_open_memory(EXR_EPUB, ...)`，读取标题/正文/章节/块 |
| 以 `<` 开头 | `exr_document_open_memory(EXR_FB2, ...)` |
| 其他 | `exr_document_open_memory(EXR_TXT, ...)` |

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

## 确定性与崩溃复现

- 变异序列只由 (seed, 语料顺序, 迭代次数) 决定，同一组合重复运行得到相同输入序列与相同 `parsed` 计数。
- 每次解析前把**即将解析的字节**写入 `--save` 文件并 `fflush`，所以崩溃后该文件就是触发输入；
  直接把它交给对应格式的解析入口即可复现。
- 正常结束打印 `fuzz: N iterations over M seeds, K reached a parsed document, no crash`。

## CI 与长跑

`.github/workflows/native.yml` 的 `fuzz` 作业用 ASan/UBSan 构建并在每次推送跑 20 万次迭代（约数分钟）；
失败时上传 `last.bin` 作为复现输入。Ctest 另有 `native-fuzz-smoke`（500 次迭代）保证驱动本身可用。

发布验收目标是每个目标持续 ≥24 CPU 小时：

```sh
./build/fuzz/exreader-fuzz --seed 20261018 --iterations 2000000000 --save /tmp/last.bin <种子...>
```

## 尚未覆盖

- 字体文件（TTF/OTF/WOFF）与布局/分页入口；
- CBZ 的固定页解码路径；
- 结构化语料裁剪（目前只做字节级变异，没有按 PDF 对象/ZIP 成员切分）。
以上随工作包 16 扩展，扩展时保持同一条「先落盘再解析」的复现规则。
