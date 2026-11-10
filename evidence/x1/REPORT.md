# X1 模型与 DOCX 双向桥验收

结论：三份 #117 原始文档往返 **18/18 一致（6 项指标 × 3 份文档）**，没有剩余不一致项。插入 5 段、修改 3 段属性后，三份文档全部保存重开成功，表格、图片、脚注、节和边距不变，编辑结果经模型重读验证。

| 指标 | minitab-ch10 | soci-syllabus | ohchr-40-69 |
| --- | --- | --- | --- |
| 段落 | 336 → 336 ✓ | 117 → 117 ✓ | 209 → 209 ✓ |
| 字符 | 13865 → 13865 ✓ | 5555 → 5555 ✓ | 71205 → 71205 ✓ |
| 表格 | 10 → 10 ✓ | 2 → 2 ✓ | 2 → 2 ✓ |
| 图片 | 17 → 17 ✓ | 0 → 0 ✓ | 0 → 0 ✓ |
| 脚注 | 0 → 0 ✓ | 0 → 0 ✓ | 5 → 5 ✓ |
| 节与四边距 | 1 → 1 节，边距逐值相同 ✓ | 5 → 5 节，边距逐值相同 ✓ | 1 → 1 节，边距逐值相同 ✓ |

节边距按 top/right/bottom/left、单位 twips：Minitab 为 1440/2160/1440/3240；SOCI 五节均为 1440/1440/1440/1440；UN 为 1417/1134/1134/1134。页大小、方向、页眉页脚引用和其他原始 sectPr 内容随原节保留。Letter 12240×15840 与边距 1440 是新模型的默认设置。

原文与输出的正文/注释文本 SHA-256、全部图片 SHA-256 均相同。编辑批次中除 document.xml 外逐 part 字节相同，数量为 minitab-ch10: 38, soci-syllabus: 25, ohchr-40-69: 31；表格、drawing、VML pict、object、脚注和尾注引用的原始 XML 片段也逐块验证 SHA-256 一致。原始脚注/尾注 part、媒体、关系、样式、页眉页脚和自定义 part 均保留。源 DOCX 留在忽略的 build/docx-inputs 下，报告不包含私人正文或失败 XML 片段。

完整 CTest：**289/289**，92.76 秒。保留 #119 的 270 组，当前分支另有 6 组 RTL/简体测试，新增 13 组桥接测试。7 组原有 fuzz 全部开启并通过。桥接覆盖原样往返、OPC 字节、未知 XML/属性、节、全部支持的属性、5+3 编辑与撤销重做、拆分删除、命名空间、新文档与字段、错误路径。补充用例覆盖节断点移动后的局部命名空间继承、default/first/even 页眉页脚引用的增删替换、负的上下边距，以及缺失 pgSz/pgMar 时的 OOXML 顺序。#117 独立校验器自测 **8/8**。

本次接续 WIP 后修复了两处可复现的节写出问题，并新增 section-boundaries 组：删除节末段落时，带正文的未知块留在原节，断点写到它后面；没有显式 sectPr 的原文在无修改时继续保持隐式节，模型页面尺寸或边距被修改后则写出显式 sectPr。注释、处理指令和空白作为间隙保留，不增加空段。新用例在修复前分别触发“opaque block moved across the section boundary”和重开后页面尺寸/边距不匹配。

发行验证中修复了既有 MinGW 配置错误：包只带 .dll.a，说明却调用 cl 链接 exreader.lib。打包说明现在按实际 import library 选择 GCC/MSVC；既有发行检查实际编译、运行包内示例并检查 PGM，未跳过检查。新文档的页眉含 dirty PAGE/DATE 域及 Times New Roman 12pt 默认样式。

19 本真书：**11,318 页、8,648,571 字形**；页数变化 **0**，逐页像素哈希变化 **0**。与 #119 保留的冻结基线比较，内容指纹相同。层检查：**121 对象，0 逆向符号依赖，0 逆向 include**。新增 docx_edit_io.c 已登记 formats 层，没有新增内部头文件。src/docx.c 与 src/export_text.c 相对任务起点逐字节未变。

实现入口在 include/exr/formats.h：exr_edit_docx_read、exr_edit_docx_open、exr_edit_docx_write。IO 调用现有 DOCX 语义解析器和 XML 文档树，额外记录源字节范围；未修改内容及未建模内容原样保留，修改的属性仅替换其已建模字段。模型继续使用 #119 的稳定 ID、事务和历史。

范围：主 XML 和包根关系支持 UTF-8/US-ASCII，UTF-16 等编码明确返回 EXR_UNSUPPORTED；复杂内联内容与表格保留为不可编辑原始 XML。手工 seed 的 p/r 模板必须有对应的原始 main part，否则拒绝写出。上述 18 项中没有由这些范围限制导致的不一致。未进行 Microsoft Word/LibreOffice 的版面比对；真书页数/哈希由仓库原有 SDK 栅格回归得到。

证据：summary.json 含源码及 DLL 哈希；roundtrip.json 为完整 18 项比较和独立格式检查的前后结果；edits.json 为编辑批次；ctest.txt 为全套日志；realbooks.json.gz 和 realbooks.diff.json 为逐页回归。基线使用 ../w1/realbooks-baseline.json.gz。

复现（本地三份输入按 tests/docx/corpus.json 的路径与 SHA-256 准备）：

```powershell
cmake -S . -B build/native -DEXR_BUILD_FUZZ=ON
cmake --build build/native -j 6
ctest --test-dir build/native --output-on-failure -j 4
python tools/docx/roundtrip.py --editable --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/roundtrip
python tests/docx/check_edit_bridge.py --manifest tests/docx/corpus.json --library build/native/libexreader.dll --output build/edited
python tools/check_layers.py build/native
python tools/regress/run_realbooks.py --manifest tools/regress/corpus.json --dll build/native/libexreader.dll --font C:/Users/Oscar/exr-deps/reader-font/Reader.otf --layout tools/regress/layout.json --workers 4 --source-revision x1-worktree-final --baseline build/baseline-books.json --output build/x1-books.json
```
