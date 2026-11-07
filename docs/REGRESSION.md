# 真书全量回归

`tools/regress/run_realbooks.py` 用公开 SDK API 逐页渲染真书，默认 4 个进程，输出计数、耗时和每页像素 SHA-256。运行只需要 Python 3.11+ 与匹配架构的 aggregate SDK DLL（`exreader.dll`，cdecl）；不依赖第三方 Python 包。不通过 GUI 或网络服务渲染。

第一份基线位于 `evidence/realbooks-baseline-20261107/baseline.json`。本地语料清单为 `tools/regress/corpus.json`，19 本：英文 13、葡语 1、意大利语 1、中文 3、日文竖排 1。前 15 本取自既有 `RESULTS.csv`，同名原件在 FinalBooks 目录，SHA-256 与 CSV 全部匹配；三本中文与竖排样本来自任务指定目录。书籍、正文、解包文件和图片不入库。

## 跑一次

以下 PowerShell 命令在仓库根目录执行。构建目录与运行输出放在仓库外。`DLL` 必须是本次要测的源码构建，`--source-revision` 是调用者填写的实际构建版本，驱动同时记录 DLL 的真实哈希，不从版本字符串猜测源码身份。

首轮编译选项和本地依赖路径保存在 `build.json`。在同一机器上可按该记录重建；换机器时先替换编译器和依赖目录，核对依赖指纹。指纹按相对路径排序，对 `.c/.h/.inc/.cmake/.in` 文件累计 `8字节大端路径长度 + UTF-8路径 + 文件SHA-256原始32字节`，排除 `.git` 和名称以 `build` 开头的目录。

```powershell
$Build = 'C:/Users/Oscar/Documents/Codex/w2-realbooks-build-20261107'
$Config = (Get-Content evidence/realbooks-baseline-20261107/build.json -Raw | ConvertFrom-Json).configuration
$Configure = @('-S', '.', '-B', $Build, '-G', 'Ninja')
$Config.PSObject.Properties | ForEach-Object { $Configure += "-D$($_.Name)=$($_.Value)" }
cmake @Configure
cmake --build $Build --target exreader --parallel 4
```

```powershell
$Dll = 'C:/Users/Oscar/Documents/Codex/w2-realbooks-build-20261107/libexreader.dll'
$Font = 'C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf'
$Out = 'C:/Users/Oscar/Documents/Codex/w2-realbooks-results'
python tools/regress/run_realbooks.py `
  --manifest tools/regress/corpus.json --dll $Dll --font $Font `
  --layout tools/regress/layout.json --workers 4 `
  --source-revision (git rev-parse HEAD) --output "$Out/baseline.json"
```

复制清单到仓库外并修改各条 `path` 即可换机器；相对路径以清单所在目录为基准。每本 `id` 必须唯一并跨运行保持稳定，`sha256` 固定原件身份；原件不符会记录错误，不能悄悄换书。缺书以 `status: missing` 留在基线中；渲染失败保留已完成页和错误阶段/状态码，整轮返回非零。只有全部书 `status: ok` 才是完整覆盖。

布局固定为 720×1040、边距 36、字号 28、行高 1.5、段间距 10，启用书内 CSS 和嵌入字体，方向为 AUTO。日文竖排由原书 CSS 指定。PDF 每页比例为 `min(1, 720 / max(native_width, native_height))`，保留页面比例。修改条件会得到另一组基线。

EPUB 按 publication 的全部 part 顺序加载，再用 `exr_pager_next` 渲染到 EOF；MOBI 使用 document pager；PDF 枚举固定页。每页 RGBA8 以白色画布渲染，哈希是按行拼接的有效像素字节 SHA-256，不包含 stride padding、PNG 编码或计时。每页同时保存宽、高、channels、全书页序号、part 和 part 内页序号；页号从 0 开始。

可重排书的 `glyph_count` 来自 `exr_layout_glyphs`，不是字符数。PDF 使用 `exr_fixed_text_regions` 的区域数；当前 PDF provider 每个有文本映射的 glyph 产生一个区域，缺少文本映射的 glyph 不计数，包含不可见文本，不能解释为全部可见字形数。`glyph_count_kind` 明示这两个口径。

## 如何用它验一个 PR

1. 在基线的同平台/架构、相同依赖版本和构建选项下，构建 PR 的 aggregate DLL。不要复用 main 的 DLL，也不要只填写 PR SHA 却运行旧二进制。
2. 使用同一份清单、字体、布局，执行下面命令。四进程完整跑完全部 19 本；输出放仓库外，保留已提交基线。
3. 检查 `candidate.diff.json` 与 candidate 的 `summary.failed_books`。差异有明确理由且经像素检查认可，才能接受；需要更新基线时，用接受后的版本完整重跑并单独审阅基线变化。

```powershell
python tools/regress/run_realbooks.py `
  --manifest tools/regress/corpus.json --dll $Dll --font $Font `
  --layout tools/regress/layout.json --workers 4 `
  --source-revision (git rev-parse HEAD) `
  --baseline evidence/realbooks-baseline-20261107/baseline.json `
  --output "$Out/candidate.json"
```

已有两份 JSON 时，无需重新渲染：

```powershell
python tools/regress/run_realbooks.py `
  --baseline evidence/realbooks-baseline-20261107/baseline.json `
  --candidate "$Out/candidate.json" --output "$Out/diff.json"
```

退出码：0 为没有差异且全部成功；1 为差异或覆盖失败需要审阅；2 为比较条件不兼容或参数错误。这个退出码是审阅闸门，不是对视觉缺陷的自动定性。

`comparable: false` 表示 schema、像素规则、布局、字体或平台/架构不同，此时先对齐条件。DLL/源码版本本来就是 PR 的比较变量，不要求相同；依赖版本和编译选项需按构建记录对齐。`source_changed` 表示语料换了，先恢复原件再判断引擎回归。

- **页数变 ≠ 回归，像素哈希变才是渲染回归信号。** 页数或字形数变化单独作为结构信息，不自动判定视觉缺陷。
- `hash_changed_pages` 列出同一全书页序号的像素或尺寸变化。未计划的哈希变化应阻止合并并调查；预期修复也会改变哈希，需要人工认可。
- `added_pages` / `removed_pages` 列出新增/消失的全书页序号，`page_count_changed` 标出页数变化。新增/消失页没有一对一像素对照，需检查原因；不能因共有页哈希相同而忽略丢页。
- 插入一页会使后续页序号整体偏移，报告可能列出大量变化。驱动按页序号比较，不做内容匹配或自动重对齐。
- 打开失败、少书、未渲染完都属于覆盖失败。耗时受并行和缓存影响，仅用于观测，没有性能回归阈值。

需要定位视觉变化时，用同一版本 SDK、同一布局和字体在仓库外渲染报告所列页。EPUB 的 `part` / `part_page` 对应此驱动的 chapter pager；不要把全书页号直接传给单 chapter API。

## 幂等与负对照

同输入完整跑第二次，添加 `--baseline` 指向第一次的 JSON。`content_fingerprint` 排除耗时与时间戳，包含原件身份、完整逐页哈希、尺寸及计数；幂等要求比较条件一致、全书成功、指纹相同、零页哈希变化。两份 JSON 的文件哈希不要求一致，因为计时和运行日期会变。

```powershell
python tools/regress/check_realbooks.py
python tools/regress/check_realbooks.py `
  --baseline evidence/realbooks-baseline-20261107/baseline.json `
  --repeat "$Out/repeat.json" --manifest tools/regress/corpus.json `
  --dll $Dll --font $Font --layout tools/regress/layout.json `
  --output "$Out/verification.json"
```

第一条验证像素 padding、哈希变化、新增/消失页、页数独立变化、增删书、缺书和条件不兼容。第二条要求两次 19 本全量结果一致，再在系统临时目录复制并实际修改《The House on Mango Street》的一个 EPUB 正文段落，重新完整渲染这一本，断言只识别到这一书的像素变化。其余 18 本沿用第一次结果。临时原件在检查后自动删除，只保留哈希、计数与差异页号。

本任务只执行本地构建与回归，不添加或运行 CI。构建身份、全量规模、两次耗时和验收结果见基线目录的运行报告。
