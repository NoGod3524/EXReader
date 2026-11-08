# Platform delivery evidence — 2026-11-08

基线 `93f9d8bb`，分支 `codex/platform-delivery-20261108`。只提交元数据、符号清单、日志和压缩逐页 JSON；二进制与 PNG 保存在仓库外 `../tmp/platform-delivery-20261108/`。

| 检查 | 结果 | 证据 |
|---|---|---|
| Windows DLL | 严格通过，389 个导出；逐个动态解析成功，SDK 3.42.0 / ABI 1 | [windows-exports.json](windows-exports.json)、[parser-integration.json](parser-integration.json) |
| Android ARM64 / macOS ARM64 / iOS 两种动态库 / Linux x64 | 389/389 契约齐全；严格模式因额外内部/第三方导出失败 | [nonwindows-strict.txt](nonwindows-strict.txt)、[nonwindows-required.txt](nonwindows-required.txt)、[export-reports.json](export-reports.json)、[symbols](symbols/) |
| Android AAR | 12,155,275 bytes；重复构建相同；32 类 / 38 native Java/JNI 一一匹配；未装机 | [aar-validation.json](aar-validation.json)、[aar-build.txt](aar-build.txt) |
| Windows 共用 C 探针 | 五项通过；实际 20 页渲染、搜索、改字号、高亮落盘重读/恢复/绘制 | [windows-acceptance.txt](windows-acceptance.txt)、[acceptance-files.json](acceptance-files.json)、[probe-build.txt](probe-build.txt) |
| ctest | 211/211，42.24 秒；复跑已有同源 Release 构建 | [ctest.txt](ctest.txt)、[ctest.xml](ctest.xml) |
| 19 本真书 | 11,484 页 / 8,648,640 字形，页数/字形数/逐页像素哈希变化均 0 | [regression-summary.json](regression-summary.json)、[realbooks.diff.json](realbooks.diff.json)、[realbooks-after.json.gz](realbooks-after.json.gz)、[realbooks.txt](realbooks.txt) |
| ABI 解析器 | Mach-O 外部/私有/未定义、ar、fat 单独切片、缺失/多余、损坏/缺失文件检查通过；Linux GNU nm 2799 个符号匹配 | [tool-tests.txt](tool-tests.txt)、[parser-integration.json](parser-integration.json) |
| 全貌命令 | 16 行，实际文件存在性/SHA/导出数与缺项状态 | [platform-status.txt](platform-status.txt)、[platform-status.json](platform-status.json)、[artifacts.json](artifacts.json) |
| 六份清单 | 每端五项、安装/加载命令、判定和限制；WASM 五项 N/A | [docs/platforms](../../docs/platforms/README.md) |

缺项保持 pending：Android x86_64 `.so`/AAR、macOS x86_64 dylib、iOS device/simulator 聚合 `libexreader.a`。没有把现有 iOS dylib 或组件 `.a` 记成目标静态库。Apple 新聚合/验收 app 代码尚未在 macOS CI 执行。所有非 Windows 本轮运行均待设备/runner；WASM 当前不支持。

CI 来源：[native run 42474080320](https://github.com/NoGod3524/EXReader/actions/runs/42474080320)。[ci-run.json](ci-run.json)、[ci-jobs.json](ci-jobs.json)、[ci-artifacts.json](ci-artifacts.json) 保留运行、成功作业和 artifact ID/名称；[provenance.json](provenance.json) 记录 Git tree 和复用构建身份。构建命令属于产物元数据，每个目标都有入口；本轮实际执行命令另见 [commands.txt](commands.txt)。

真书首轮误用了不同的字体参数，比较器因 `font_sha256` 不同拒绝，日志保留在 [realbooks-font-mismatch.txt](realbooks-font-mismatch.txt)。已按基线 Reader.otf 重新渲染全部 19 本，最终 diff 可比较且为零变化；没有修改基线或比较器。

## 复查

```sh
python tools/abi/test_check_exports.py
python tools/abi/platform_status.py
python tools/abi/check_exports.py ../tmp/platform-delivery-20261108/delivery/windows/x86_64/exreader.dll
```

Windows 真书复跑使用 [docs/ui/acceptance/check_font_manager_host.py](../../docs/ui/acceptance/check_font_manager_host.py)，基线是仓库已有 `docs/ui/evidence/annotations/books-after.json`；完整本轮逐页报告仅压缩存储元数据，不包含书籍正文。`PLATFORMS-OUT.txt` 按完成步骤追加。
