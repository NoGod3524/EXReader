# PowerPoint hybrid xref 修复与恢复验收

分支：`codex/pdf-xref-stream-20261111`。Draft PR：<https://github.com/NoGod3524/EXReader/pull/133>，目标 `main`，不合并。

## 实际根因和改动

任务书 P1/P2 的根因描述均与现有代码不完全一致。基线 `f9df237713c9ad36d0cf6bb10df6b58fbc30ccff` 已有 xref stream、ObjStm、PNG predictor 和 `/XRefStm` 支持。

`deck.pdf` 的 supplemental xref stream 是 `1038 0 obj`，该流字典的 `/Size` 也是 1038；最终传统 trailer 的 `/Size` 是 1039。原 `stream_xref()` 的 `object>=size` 检查拒绝了这个 Office 文件。

| 位置 | 本分支改动 |
| --- | --- |
| `src/pdf_objects.c:341-343` | 在 hybrid 模式下允许流自身对象号不在该流 `/Size` 范围内；保留全局对象号上限，纯 stream 模式仍保留原检查。 |
| `tests/test_pdf_hybrid.c:10` | 对真实 deck 断言打开成功、15 页、15 页全部渲染成功，并输出首帧计时。 |
| `tests/test_pdf_hybrid_xref.c:56` | 内存构造 merge、Office `/Size` 情况、`/Prev` 链和非法偏移场景。 |
| `CMakeLists.txt:814`、`:1012` | 注册四组测试，并沿用既有测试配置链接 `pdf_crypto.c`。 |

复用的实现保持原样：

- `/W`：三个大端变长字段；第一个宽度为 0 时默认类型 1，其他缺失字段为 0。
- `/Index`：按起点/数量对解码；缺省使用 `[0 /Size]`。
- Flate 和 predictor：既有流解码器先解压，再执行 `undo_predictor()` 的 PNG 行重建。
- `/XRefStm`：`classic_xref()` 已调用 `stream_xref(..., hybrid=1)`；同 revision 的 stream 条目覆盖传统表，传统表独有条目保留，旧 revision 不覆盖新 revision。
- `/Prev`：继续沿传统 trailer 指定的 revision 链加载。
- ObjStm：type-2 条目仍由 `compressed_object()` 读取 `/N`、`/First` 及对象索引。

本样本的 xref stream 使用 Flate，未带 `/DecodeParms`；predictor 回归由既有 `pdf-xref-predictor.pdf` 和 `pdf-hybrid-predictor.pdf` 等夹具覆盖。

## 修复前失败断言与修复后探针

恢复时引擎和测试已提交。本轮未重写实现；将基线版本的 `pdf_objects.c` 单独编译，替换现有 Release 构建中的对应对象并重新链接到 `build/hybrid-validation/libexreader.dll`，其余对象和依赖相同。原始测试可执行文件在此 DLL 下失败：

```text
deck line 14: (exr_fixed_open(path,((void *)0),&d,&error))==EXR_OK (5: Invalid PDF cross-reference stream)
exit=1
```

修复前 `fixed_open`：

```json
{"status":5,"pages":0,"message":"Invalid PDF cross-reference stream"}
```

修复后独立探针，`perf_counter()` 墙钟计时：

```json
{"status":0,"pages":15,"rendered":15,"failures":0,"first_paint_ms":6068.751}
```

本轮 ctest 的同一夹具输出：`pages=15 rendered=15 failures=0 first_paint_ms=4660.0`。该 C 测试使用 `clock()`，与独立探针计时口径不同。

原始记录见 [baseline-assertion.txt](baseline-assertion.txt)、[baseline-probe.json](baseline-probe.json)、[deck-probe.json](deck-probe.json)。deck 为 286,561 字节，SHA256 为 `b1549f6bdb6c3d51c456e5222ba8efaa7487558e6d2ace106bdb4059d8ef2204`。

## 影响面

扫描 `git ls-files '*.pdf'` 的全部 1,036 个 PDF，使用行首 `xref` 和 `/Type /XRef` 判断类型。两者并存包括增量更新文件；其中 3 个明确含 `/XRefStm`。

| 引用类型 | 文件数 | 修复前 fixed_open 成功 | 修复后成功 |
| --- | ---: | ---: | ---: |
| 传统表 | 1001 | 880 | 880 |
| xref stream | 29 | 7 | 7 |
| 两者并存 | 5 | 4 | 5 |
| 无法按上述标记归类 | 1 | 0 | 0 |
| 合计 | 1036 | 891 | 892 |

夹具包含损坏输入、需口令输入及不满足完整页面文档要求的输入，因此不能把所有打开失败都视为缺陷。逐文件比较状态、页数和错误消息，**唯一变化是 `tests/fixtures/pdf-ppt/deck.pdf` 从失败变为成功**。完整记录见 [inventory.json](inventory.json)。

另对 `pdf-graphics.pdf`、`pdf-xref-stream.pdf`、`pdf-hybrid.pdf` 的所有页面在基线和修复后逐字节比较 RGBA，结果相同，像素哈希见 [unchanged-pixels.json](unchanged-pixels.json)。

## CTest 与新增组

使用既有 `build/h` MinGW Release 构建。本轮结果：

```text
ctest --test-dir build/h -R '(native-pdf-|fixed)' -j 2 --output-on-failure
100% tests passed out of 46
Total Test time (real) = 56.29 sec

ctest --test-dir build/h -R '^(native-pdf_edit-component|sdk-doc-pdf)$' --output-on-failure
100% tests passed out of 2
Total Test time (real) = 2.39 sec
```

全部 48 组相关测试在这两次执行中通过。日志：[ctest.txt](ctest.txt)、[ctest-additional.txt](ctest-additional.txt)。上一轮 `build/x` 的缺少可执行文件和 Ninja 重整失败日志不作为本次验收证据。

新增四组：

1. `native-pdf-hybrid-deck`：真实 deck 打开、页数、全页渲染。
2. `native-pdf-hybrid-merge`：同 revision stream 优先、传统表独有项、stream 独有项，以及流对象号等于 `/Size`。
3. `native-pdf-hybrid-chain`：`/Prev` 增量链与 `/XRefStm` 同时存在。
4. `native-pdf-hybrid-bad-offset`：零、非对象位置和越界偏移返回明确 `EXR_FORMAT`，输出对象为空。

## 独立像素对比

系统无 `pdftoppm`；使用已安装的 PyMuPDF，15 页均以 1 倍比例渲染，输出 960×540，RGBA 合成到白底后比较 RGB。

| 页 | 平均每通道绝对误差（0–255） | 最大通道误差 |
| --- | ---: | ---: |
| 1 | 1.510102 | 136 |
| 2 | 1.517249 | 136 |
| 3 | 1.516635 | 136 |

15 页平均每通道绝对误差范围为 1.510102–1.523418；最大单通道误差为 140。**不是像素完全一致**；逐页结果见 [pixels.json](pixels.json)。前 3 页的两套 PNG 已目视核验，文字、表格和图形布局一致。PNG 位于 `build/hybrid-validation/{exreader,reference}-{1,2,3}.png`。

## 边界与交接

- `tests/check_reading_release.py` 未改，SHA256：`6eb22a304686b2160d1f283a709936bfdfd65c3b0f5e10bb060f457c4faffb2b`。
- `tools/version_literal_exceptions.json` 未改；没有新增 `src/*.h`。
- 本任务没有修改 `src/docx_*`、`src/export_text.c`，没有启动 GUI、SendInput 或修改系统设置。
- 恢复时未提交的 `OUT2.txt` 已原样保存为 [recovered-OUT2.txt](recovered-OUT2.txt)。原文件与 `origin/main` 对齐，以消除无关日志的 add/add 冲突。
- `CASCADE-CLAUDE-OUT.txt` 是先前会话的历史记录；完成状态以本报告及原始验收数据为准。

复现：`python -X utf8 evidence/pdf-hybrid-20261111/verify.py`。该脚本使用现有 `build/h`、MinGW、NumPy、Pillow 和 PyMuPDF，所有基线编译产物写入忽略的 `build/hybrid-validation/`。
