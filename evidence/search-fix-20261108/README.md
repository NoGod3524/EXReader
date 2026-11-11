# #83 搜索 API 撞名修复

流式搜索从 `exr_document_search` / `exr_document_search_all` 改名为 `exr_publication_search` / `exr_publication_search_all`；声明、实现、Windows 宿主、C 测试和 ctypes 动态符号同步更新，搜索逻辑未改动。PDF `exr_document_search` 的声明和实现保留。

撞名清单只有 `exr_document_search`。`layout.h` 与 main 的 `document.h` 全部公开函数声明交集为空；`layout.h` 中 `exr_document_` 仅出现在说明偏移对应 `exr_document_text` 的注释。`document.h` 与 main 内容一致。三个搜索符号均已从重新构建的 DLL 加载，详见 [api-audit.json](api-audit.json)。

```c
EXR_API exr_status exr_publication_search(
  exr_publication *publication, exr_text_position from,
  const char *needle, unsigned flags, const exr_control *control,
  exr_search_result *result, exr_error *error);
EXR_API exr_status exr_publication_search_all(
  exr_publication *publication, const char *needle, unsigned flags,
  exr_search_fn callback, void *context, const exr_control *control,
  size_t *count, exr_error *error);
```

| 验收 | 结果 | 证据 |
| --- | --- | --- |
| Windows Release 全量构建 | 成功 | [build.txt](build.txt) |
| Linux / Android ARM64 / ASan+UBSan | 三个作业全部成功；Linux ctest **201/201**，ASan+UBSan ctest **198/198** | [Actions run 42463330179](https://github.com/NoGod3524/EXReader/actions/runs/42463330179)、[最终作业快照](ci-builds.json)、[Linux 测试](linux-ctest.txt)、[sanitizer 测试](sanitizer-ctest.txt) |
| 全量 ctest | **208/208**，79.75 秒；含 5 组流式搜索、5 组 PDF 深化 | [ctest.txt](ctest.txt) |
| 三书各 5 词 | **15/15**；计数与原验收及独立 Python oracle 一致 | [search.json](search.json) |
| 真书命中位置 | **20/20**，含 6 个竖排；定位、锚点、实际字形均一致 | [search.json](search.json) |
| 19 本真书逐页渲染 | **19/19、11,296 页、8,648,640 字形**；页数、字形数、逐页像素哈希变化均 **0** | [diff](realbooks.diff.json)、[before](realbooks-before.json.gz)、[after](realbooks-after.json.gz) |
| Windows 搜索栏 | 中文、英文、竖排、PDF、MOBI、整书导入 **6/6**；计数、前后跳转、关闭、大小写、全词、自检通过 | [ui.json](ui.json)、六份 `ui-*.txt` |
| 连续输入 10 字 | 防抖后实际搜索 1 次，搜索 1.890ms；含输入间隔和防抖总 675.841ms | [ui-hong.txt](ui-hong.txt) |

测试总数按构建配置区分：Windows 208 项包含 7 项既有 fuzz；Linux 常规套件为 201 项；sanitizer 配置按现有 CMake 规则排除 3 项性能测试，为 198 项。

重新编译的宿主截图已目视核验：[中文搜索栏](expanded-current.png)、[下一命中](next-current.png)、[竖排高亮](vertical-current.png)。

本目录证据对应代码提交 `90bfd3cc899e89b8e6af51204fcb6a330f8803a8`；后续提交只追加验收记录。构建命令、源码与产物哈希见 [host-commands.json](host-commands.json)、[provenance.json](provenance.json)。19 本回归沿用原验收的 DLL 报告、字体、布局配置逐页比较。复跑入口：

```powershell
cmake --build build/search --parallel 6
ctest --test-dir build/search --output-on-failure -j 4
python -X utf8 tests/check_document_search.py build/search/libexreader.dll tests/search-fix-20261108/search.json
python -X utf8 examples/windows/check_shell_search.py build/search-fix-host/EXReader.exe C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf build/search-fix-ui
python -X utf8 tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/search/libexreader.dll --font C:/Users/Oscar/Documents/Codex/EXReader-Windows-delivery-20261104/payload/Reader.otf --layout tools/regress/layout.json --output build/search-fix-realbooks.json --baseline build/search/realbooks.json --workers 4 --source-revision 90bfd3cc899e89b8e6af51204fcb6a330f8803a8
```
