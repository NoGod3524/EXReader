# T1：30 个原创混合 DOCX 夹具

所有文字、数字、PNG 像素和图形均由 `generate.py` 原创生成，按本仓库 MIT 许可分发。没有复制书籍或课程资料。ZIP 时间戳固定、部件排序固定；`manifest.json` 记录每份文件的 SHA-256、字节数、结构特征和唯一编辑目标。

每份夹具组合正文、表格、PNG、脚注、页眉／页脚、域、样式、编号与主题；专门覆盖的 30 种结构见 manifest。重复表头用 89 行表格模拟实际跨页表格。结构特征、关系目标存在性及原创生成结果都由测试断言。

```powershell
python tests/fixtures/docx-real/codex/generate.py --check
python tests/fixtures/docx-real/codex/run_matrix.py --library build/native/libexreader.dll --output build/t1/after
python tests/fixtures/docx-real/codex/oracle_mutations.py
```

`run_matrix.py` 调用公开可编辑 DOCX ABI，没有调用文本导出器。无修改和改字两条路径使用独立模型，分开记录。改字目标所在段落包含相应的域／书签／锚点／节属性；表格夹具则改其邻近正文。先构造“仅替换唯一目标文字”的独立 expected.docx，逐项比对实际输出，记录允许的字符数变化和额外损失；不豁免整个段落，也不忽略主文档。

18 项指标由原 #117 六项原函数、其原有文本／图片哈希，以及新增的十项部件／结构检查构成。矩阵之外还要求所有 OPC 部件与独立 expected 完全相等，并验证保存、重开、再保存稳定。18 项指标各有故意损坏的负对照。

原 #125 没有改正文文字的命令。修前用公开 `exr_edit_doc_create` 深拷贝保留全部 ID、模板和 OPC 部件的模型快照，仅替换目标 run；修后使用新增 `exr_edit_set_run_text`。`--legacy-snapshot` 只用于明确标记的历史对照，默认路径必须使用公开文字命令。

## CTest 登记与完整验收

用户限定不能修改根 `CMakeLists.txt`，因此通过 CMake 原生 `CMAKE_PROJECT_INCLUDE` 与 deferred call 登记测试。原有测试保持原样。以下配置在完成原仓库依赖配置的 build 目录执行：

```powershell
$t1Hook = (Resolve-Path tests/fixtures/docx-real/register.cmake).Path
cmake -S . -B build/native "-DCMAKE_PROJECT_INCLUDE=$t1Hook"
cmake --build build/native -j 2
# MinGW 下为原 SDK smoke 生成实际 DLL 的 MSVC 导入库：
New-Item -ItemType Directory -Force build/native/Release
& 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/HostX64/x64/lib.exe' /nologo /machine:x64 /name:libexreader.dll /def:build/native/exreader.def /out:build/native/Release/exreader.lib
ctest --test-dir build/native --output-on-failure -j 2
```

新增 70 个 CTest：30×2 条矩阵路径、1 项生成复现、7 项针对性回归、1 项 18 指标负对照、1 项文字命令分配失败测试。最后一项逐个注入分配失败，验证事务内外的原子回滚和零泄漏。

## 重建修前与逐项修复证据

`build_control.py` 复用已有 MinGW 构建的依赖和未变化对象，逐文件验证其产品源码与指定 Git 提交一致；重编译原提交的模型、IO 和公开头，生成完全独立的对照 DLL。元数据包括源哈希和 DLL 哈希。

```powershell
python tests/fixtures/docx-real/codex/build_control.py --build build/native --output build/t1/control
python tests/fixtures/docx-real/codex/run_matrix.py --library build/t1/control/libexreader.dll --legacy-snapshot --output build/t1/before
python tests/fixtures/docx-real/codex/regressions.py --library build/t1/control/libexreader.dll paragraph-markers
python tests/fixtures/docx-real/codex/regressions.py --library build/native/libexreader.dll paragraph-markers
```

修前矩阵和针对性回归应返回非零。`--stage text` 重放仅增加文字命令的状态；`--stage paragraph` 再加入段落前导标记修复。两者仍应因尚未修复的节尾漂移返回失败。最终 CMake 构建包含全部修复。未改变同一断言的通过标准。

结果、30 行表、18 项汇总、原始压缩矩阵和 19 本真书逐页哈希在 [docs/DOCX-REAL-RESULTS.md](../../../../docs/DOCX-REAL-RESULTS.md)；能力边界见 [DOCX-LIMITS.md](../../../../docs/DOCX-LIMITS.md)。
