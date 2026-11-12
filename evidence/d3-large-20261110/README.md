# d3-large 收尾证据

完整结论、命令和限制见仓库根目录 `OUT.txt`。

- `ab-claude.json`：从上一会话恢复的完整交错 A/B，7 本 × 2 侧 × 5 次。不是已判定受负载污染的 `measure-after2.json`。原始两侧 probe 二进制不同，不能将其耗时差直接归因于搜索缓存修复。
- `ab-sameprobe.json`：本次用相同 probe 补测 5,901／10,964／26,013 页，每侧各 5 次；记录各次原值、中位数和最小值。A/B 交错顺序每轮反转，同一时刻只运行一个 probe。
- `ab-*-summary.csv`：上述 JSON 的测量表。耗时单位 ms，内存单位 MiB；turn/jump p95 来自每次 20 个固定种子抽样。
- `merged-v*.json`：Claude 已完成的全书顺序分页及内存曲线。这一模式不逐页绘制；measure 模式对首屏、抽样跳转／翻页和末条目录落点绘制 RGBA 页面。
- `v*.meta.json`、`v*.pages.txt`、`sources.json`：测量样本的体积、散列、组成和各章节页数。v12 使用 12 本不同的公版书，v24 将这 12 本重复一遍；后者只作为极端规模样本。原始书籍保留在工作树旁 `../large-book-d3/`。
- `ctest.txt`、`search-bounded-*.txt`：当前合并树的完整测试，以及同一 bounded-search 测试在当前／修复前 DLL 上的正反对照。
- ctest 首轮 256/257 通过，`sdk-release` 在 180 秒超时；单项重跑在 54.46 秒明确失败于 README 的 MSVC 链接命令缺少 `lib/exreader.lib`。当前 MinGW 包提供的是 `lib/libexreader.dll.a`。`ctest-sdk-release-retry.txt` 和 `sdk-*.json` 保留发布门禁失败及包校验结果；`package-gcc-smoke.txt` / `.json` 记录同一包使用匹配 MinGW 工具链编译、执行及非白图像检查通过。该补测不替代原 MSVC quickstart 门禁。
- `realbooks-after.json.gz`、`realbooks.diff.json`、`realbooks-summary.json`：19 本真书的逐页哈希、比较及摘要。有效基线是已有的 `evidence/perf-gate-final-20261109/realbooks.json.gz`，字体 SHA256 为 `a4aed998…`。
- `realbooks-font-mismatch.diff.json.gz`：第一次比较使用旧字体基线的诊断记录，`comparable=false`、`incompatible_conditions=["font_sha256"]`。同名系统字体文件的内容已变化；最终比较改用字体哈希一致的已有基线，没有修改任何基线或测试断言。
- `hashes.json`、`build-options.txt`、`deps.args.txt`、`host-during-ab.json`：二进制及保护文件散列、构建选项、离线依赖路径、共享宿主机负载快照。A 为修复前冻结 DLL `bea067b7…`；B 为本树已有 Release DLL `1137bc5e…`。补测两侧 probe 都是 `803a0a17…`。

SDK probe 镜像 Windows reader 的 bounded pager 和首批 32 条搜索路径，布局 720×1040、字号 28；workspace 8 MiB，窗口 64 KiB，页面缓存 2 页／32 MiB，checkpoint 8 个／4 MiB／每 8 页。它测量 SDK 路径，不包含窗口消息队列和屏幕呈现延迟。共享宿主机还有其他编译／测试进程，耗时结果保留波动，不能作为空闲机器性能承诺。

在相同本地样本、字体和 DLL 目录下复跑：

```powershell
ctest --test-dir build/d3 --output-on-failure -j 2
python tools/large_book/ab_measure.py --a ../large-book-d3/A-sameprobe --b ../large-book-d3/B-sameprobe --font ../large-book-d3/Reader.otf --runs 5 --output ab-repeat.json ../large-book-d3/books/v4.epub ../large-book-d3/books/v7.epub ../large-book-d3/books/v12.epub
```

19 本像素回归使用 `tools/regress/run_realbooks.py`、`tools/regress/corpus.json` 和 `tools/regress/layout.json`。解压现有基线和本目录 candidate 后，用 `--baseline ... --candidate ... --output ...` 比较即可。字体应核对文件内容散列，不能只核对文件名。
