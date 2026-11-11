# X2 编辑重排接口

`exr_edit_pager_create` 将 X1 编辑模型接到现有 `exr_pager_get` 和渲染接口。`exr_edit_layout_after` 自动比较上次已排版快照，汇总事务、删除、插入、拆段、属性修改、撤销和重做的影响；传入的块 ID 只是提示，不会漏掉其它修改。

```c
#include <exr/reflow.h>

exr_pager *pager = NULL;
exr_edit_view_anchor before, after;
size_t pages_repaginated = 0;
exr_edit_pager_create(doc, font, &config, &pager, &error);
exr_edit_anchor_capture(pager, page_index, block_id, byte_offset, &before, &error);
/* 在此调用 X1 修改命令；批量操作可包在一个事务中。 */
exr_edit_layout_after(doc, pager, block_id, &pages_repaginated, &error);
exr_edit_anchor_restore(pager, &before, &after, &error);
/* 用 after.page_index + after.page_offset 恢复文字锚点，并保留原来的像素位移。 */
exr_pager_get(pager, after.page_index, &page, &error);
exr_render_page_color(page, font, 0, &bitmap, &error);
```

每个调用的返回状态均需检查。模型与字体按既有所有权规则管理，释放 pager 后释放模型；也可以在 layout_after 中提交保留块 ID 的新模型快照，成功后替换绑定模型。

块 ID 不按数值排序。脏区记录同时保存旧、新文档顺序的半开块区间及旧文档的半开页区间。通过页内行位置定位起始页；单段跨页时，完整 shaping 旧、新段落以检查行前缀，只重新分页包含不同内容的页及其后续。浮点页高相同，且进入已验证不变的后缀后，页首块和段内续排行同时匹配旧页即可停止。不能仅比较页首块 ID。

行几何保留在段落快照中，未改段落不重复 shaping。字形与像素没有第二套文档缓存；页负载仍使用 pager 原有 1–64 页 LRU 和 byte_budget。完整上一页装不下新增段落时保留它的缓存，文末追加直接生成新页。收敛后的缓存页调整页索引及源字节位置，保留字形几何。失败或取消不提交新目录、不失效旧缓存。

锚点的 byte_offset 是块内各 run 拼接后的 UTF-8 字节位置，page_offset 是相对于新页 source_start 的字节位置。源投影每块额外占一个分隔字节；glyph.node 为稳定块 ID。锚点支持当前及上一个成功修订，插入采用右亲和；拆段跟随右侧文字，删除文字收缩到替换区末端，删除块优先落到下一个存活块。宿主保存文字锚点相对视口的像素位移。

当前支持纯文字段落、run 字体/字号/粗斜体/颜色、段落对齐/缩进/间距/keep-lines、段前分页和显式分页符。opaque run、表格、未建模 XML、编号、keep-next 与 user CSS 返回 EXR_UNSUPPORTED。页大小取宿主 config；不应用 DOCX 节纸张大小。当前快照检测扫描 O(块数 + 文字字节数)，不会遍历重排未受影响的页；X1 尚未提供逐命令变更日志或替换文字命令，因此未侵入其实现添加钩子。

X2 没有修改或复制 `src/docx_edit.c`。`include/exr/edit.h` 来自 X1 的公开接口快照；构建时通过 `EXR_EDIT_MODEL_SOURCE` 指向 X1 文件。合并 X1 后默认使用本仓库的 src/docx_edit.c；缺失模型时重排接口返回 EXR_UNSUPPORTED，其余阅读引擎可正常构建。新内部头已登记 tools/layers.json。

```powershell
cmake -S . -B build/native -G Ninja -C build/native-init.cmake -DCMAKE_BUILD_TYPE=Release -DEXR_EDIT_MODEL_SOURCE=C:/Users/Oscar/Documents/Codex/EXReader-x1-bridge-20261110/src/docx_edit.c -DEXR_ENABLE_IMAGE_WEBP=OFF -DEXR_ENABLE_IMAGE_TIFF=OFF -DEXR_ENABLE_IMAGE_AVIF=OFF -DEXR_BUILD_JNI=OFF -DEXR_BUILD_FUZZ=OFF
cmake --build build/native --parallel 6
ctest --test-dir build/native --output-on-failure -j 6
build/native/exreader-reflow-test.exe tests/fixtures/fonts/primary.ttf benchmark
```

本机 native-init.cmake 只指定已有依赖源码位置；可改用常规 FetchContent 获取固定依赖。MinGW 构建的 SDK 若要运行现有 MSVC README 冒烟测试，需从 exreader.def 生成 Release/exreader.lib，DLL 名为 libexreader.dll；本次生成命令保存在 evidence/x2-reflow-20261110/msvc-import-library.log。公开头文件已加入 SDK 发布清单。

数字、缓存命中数、锚点示例与 19 本真书哈希对照见 [验收记录](../evidence/x2-reflow-20261110/README.md)。
