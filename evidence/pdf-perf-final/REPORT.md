# PDF 渲染性能终态（main @ 1bfb83ede）

## 结论

| 指标 | PDF.js 对照 | EXReader | 结论 |
| --- | ---: | ---: | --- |
| 1200 px 首屏 | 13 ms | **3.388 ms**（p50，最大 4.231） | 3.8× 更快 |
| 1200 px 翻页 | 4 ms | **3.487 ms**（p50，best 3.445，p95 4.381） | 更快 |
| 600 px | — | 1.925 ms | — |
| 2400 px | — | 11.912 ms | — |
| 图像密集 word-5 @1200 | — | 25.681 ms（#236 前 33.265） | −23% |

## 条件

- 机器：Intel Ultra 7 256V，MinGW GCC 16.2，Release，`EXR_ENABLE_PDF=ON`、`EXR_IMAGE_AVIF=OFF`、`EXR_BUILD_TOOLS=OFF`
- 夹具：`tests/fixtures/pdf-hybrid-real/pptx-20.pdf`（20 页），SHA-256 `2bfb94aa6905f27915e309b3c820fef3ba13492dddedfb93d97a10e8d7679729`
- 计时口径：`tools/benchmark_pdf_rect.py` 只包住 `exr_fixed_render`，拷贝/哈希/PNG 在计时窗口外
- 空载：测量时 CPU 14–23%；runs 20、repeat 3，三次之间 spread 0.1% / 1.3% / 0.5%
- `open_ms`：600/1200/2400 分别为 0.116 / 0.098 / 0.109 ms

## 正确性

- 逐像素：60 个 page/width 组合，**85,056,000 个 active RGBA，非零差异 0，最大通道差 0**（`pixel-diff.json`）
- CTest：`100% tests passed out of 577`

## 改动来源

| PR | 内容 | 效果 |
| --- | --- | --- |
| #232 | 矩形解析覆盖率快路径 + 图层按行批处理 | 首屏 22.18 → 10.93 ms |
| #234 | 整页 clip 早退（解锁无 mask 快路径） | 1200px 5.61 → 3.56 ms |
| #236 | 影像像素查表复用 | word-5 33.3 → 25.7 ms |

## 复现

```powershell
$K = "C:\Users\Oscar\exr-deps-cache"
cmake -S . -B build/perf -G Ninja -DCMAKE_BUILD_TYPE=Release `
  -DEXR_ENABLE_PDF=ON -DEXR_ENABLE_PDF_EDIT=ON -DEXR_BUILD_TESTS=ON `
  -DEXR_BUILD_TOOLS=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF `
  -DFETCHCONTENT_SOURCE_DIR_FREETYPE="$K\freetype-src" `
  -DFETCHCONTENT_SOURCE_DIR_MBEDTLS="$K\mbedtls-src" `
  -DFETCHCONTENT_SOURCE_DIR_ZLIB="$K\zlib-src" `
  -DFETCHCONTENT_SOURCE_DIR_EXPAT="$K\expat-src" `
  -DFETCHCONTENT_SOURCE_DIR_MINIZ="$K\miniz-src" `
  -DFETCHCONTENT_SOURCE_DIR_LIBWEBP="$K\libwebp-src" `
  -DFETCHCONTENT_SOURCE_DIR_LIBTIFF="$K\libtiff-src" `
  -DFETCHCONTENT_SOURCE_DIR_OPENJPEG="$K\openjpeg-src" `
  -DFETCHCONTENT_SOURCE_DIR_SQLITE="$K\sqlite-src" `
  -DFETCHCONTENT_SOURCE_DIR_STB="$K\stb-src" `
  -DFETCHCONTENT_SOURCE_DIR_MINIMP3="$K\minimp3-src" `
  -DFETCHCONTENT_SOURCE_DIR_LCMS="$K\lcms-src"
cmake --build build/perf --parallel 6
python -X utf8 tools\benchmark_pdf_rect.py capture `
  --library build\perf\libexreader.dll `
  --input tests\fixtures\pdf-hybrid-real\pptx-20.pdf --expect-pages 20 `
  --output out --widths 600 1200 2400 --runs 20
```

## 已知未做

- `#235` 的 canvas 区域缓存在 600px 有 +71% 回退，未合入
- 位图复用可再省 0.612 ms/页（16%），卡在跨 TU 所有权，补丁见 `projects/exreader-handoff/PATCH-bitmap-pool-wip.diff`
- 字形覆盖率 atlas 未落地
