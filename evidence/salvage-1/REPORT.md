# SALVAGE-1 验收报告

基线：`origin/main` = `953a7644223000e0705a78287e0c3e68646e9f3e`。
全新工作树：`<workspaces>/EXReader-salvage-main-20261114`。
分支：`codex/salvage-ppt-intent-20261114`；PR base：`main`。

原 patch 与 `<verification-workspace>/salvage/` 的副本 SHA-256 一致：

- pptx-m5.patch（11027 bytes）：`E592BC20E3D8C5331BA9757D674927D5180AC47CA4F562CF0900E64FA47D8201`
- ppt-m4.patch（14461 bytes）：`B258D3F25FE74C50FDDF0CAFC1D3309088D9733A6A039FE2EDBD269D8913852D`

## A–E 逐项结论

| 项 | 结论 | main 中的缺口、移植方式与正确性依据 |
|---|---|---|
| A | 已移植 | main 在 transform 成功后才数 tc，畸形 frame 提前返回可以绕过上限。读取 tr 时计数并保存 row_cells，让结构限制独立于能否绘制；绘制复用计数。测试覆盖 201 tc 配六种畸形几何，并验证 200×200 仍合法。 |
| B | 已移植 | main 没有 table-cjk 测试组。复用 test_pptx_text.has_cjk_font；有字体时验证四种独立字形轮廓，并与同尺寸文本框逐像素比较；无 CJK 字体时验证回退诊断与相同回退栅格。正常输入仅接受字体诊断；有 CJK 字体时禁止 missing 字符，无 CJK 字体时允许预期的逐字符 missing 回退诊断。 |
| C | 已移植 | main 使用 styles[kind][i ? i-1 : 0]。先解析并校验 level，再以 styles[kind][level] 为底叠加显式属性，保留同文档对应层级默认值，避免上一层覆盖泄漏。测试分别覆盖首层未指定与覆盖 36pt 时，次层仍为 48pt/右对齐。 |
| D | 已移植 | main 的字符 overlay 仅用于文本 run；段落本身仍用未 overlay 的样式。按段起点推进 CF 游标并叠加段落样式，空段的 CR 字符属性因此提供正确字号；空行用去掉下划线的 NBSP 提供字体度量，保留前导/连续空行且不产生墨迹。 |
| E | 已移植 | 添加 master/spacing 回归断言、placeholder/master 合成能力；保留 M6 的 extra_shapes 参数及结构警告断言。新增正常用例仅容忍 font fallback 警告。 |

对应完整 diff：[`intent.diff`](intent.diff)。

## 关键 diff 片段

A：计数发生在 transform 之前；绘制阶段复用结果。

```diff
+    for(j=xml->nodes[i].first_child;j!=SIZE_MAX;j=xml->nodes[j].next_sibling)
+      if(named(&xml->nodes[j],A,AS,"tc") && ++count>MAX_TABLE_DIMENSION)
+        return exr_fail(e,EXR_LIMIT,"PPTX table row cells exceed 200");
+    row_cells[rows]=count;
...
+    size_t count=row_cells[r];
```

B：宿主字体分流与四字形轮廓验证。

```diff
+from test_pptx_text import bands, bounds, has_cjk_font, mask
+    elif group == 'cjk':
+        cjk = has_cjk_font()
...
+        assert image.data == reference.data
+        if cjk:
...
+            assert len(set(silhouettes)) == 4
```

C：初始化来自解析出的对应层级。

```diff
-    text_props p=styles[kind][i ? i-1 : 0];level=(unsigned)i;
+    text_props p;level=(unsigned)i;
+    if((kind>=5 && !text_u16(r,&at,a->end,&level)) || level>=5) { r->drawing->text_malformed++;return; }
+    p=styles[kind][level];
```

D：段落起点的字符属性与空行度量。

```diff
+    paragraph=p;
+    while(k+1<cc && start>=cf[k].end) k++;
+    if(cc) text_cf_overlay(&paragraph,&cf[k].props);
...
+  blank_style.flags&=~EXR_GLYPH_UNDERLINE;
...
+        if(model->node_count==bullet_end || model->nodes[model->node_count-1].kind==EXR_NODE_BREAK)
+          status=text_add(model,&spans,&capacity,"\xc2\xa0",2,&blank_style,e);
```

E：真实栅格对照与行距、无墨迹断言。

```diff
+                assert abs(gap - 2 * advance) <= 2, (repr(text), rows, advance)
+                assert abs(offset - advance) <= 2, (repr(text), offset, advance)
+                assert not mask(image), repr(text)
...
+                    assert actual.data == explicit.data, (first_size, level, stats(actual), stats(explicit))
```

## 额外 hunk 与跳过项

- PPTX patch 7 个 hunk 全部按当前 main 上下文移植，包括 CMake 测试注册、namespaces 与 invalid-spans 两组覆盖。
- PPT patch 15 个 hunk 中，14 个移植；测试生成器中两个 hunk 与 M6 的 extra_shapes 上下文不同，手工合并并保留该能力。
- 跳过 docs/PPT-M4.md 的旧验收记录 hunk：它写死“79 次检查”和 evidence/ppt-m4/reverify-text-tests.txt，属于旧 lane 的历史运行结果。本轮数据与日志记录在此目录。
- A–E 中没有“已在 main，跳过”的项目。main 已有的 run 级 text_cf_overlay、extra_shapes 和 M6 警告完整性测试保留复用。
- tests/check_reading_release.py 未修改。

## 回归证明

[`baseline-regressions.txt`](baseline-regressions.txt) 为新增断言对已有 M6 构建产物的运行结果（不是本轮重编的 main）：limits、master、spacing 均 exit 1，分别暴露畸形 frame 绕过上限、跨层错误继承、空行字号丢失。源码对照见 intent.diff。

## 验收输出

构建：完整新目录构建，exit 0；编译日志逐行统计 error=0、warning=0。

```text
[1281/1282] Building CXX object _deps/libaom-build/CMakeFiles/yuv.dir/third_party/libyuv/source/row_common.cc.obj
BUILD exit=0 errors=0 warnings=0
```

- [`configure-arguments.json`](configure-arguments.json)：全功能配置的完整参数，使用本机已有第三方依赖源码，未复用旧 lane 的编译对象。
- [`configure-final.txt`](configure-final.txt)：配置输出。
- [`build.txt`](build.txt)：全部构建输出。
- [`build-summary.txt`](build-summary.txt)：构建结果与诊断计数。
- [`targeted-tests.txt`](targeted-tests.txt)：19/19 定向测试的完整 verbose 输出；15 个 native-ppt-text-* 组共 83 次检查。

定向命令：

```powershell
ctest --test-dir build/salvage -V -R '^(native-pptx-table-(cjk|limits|namespaces|invalid-spans)|native-ppt-text-.*)$'
```

实际新增/加强测试输出节选：

```text
82: 201 tc + missing xfrm: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
82: 201 tc + missing off: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
82: 201 tc + missing ext: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
82: 201 tc + negative cx: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
82: 201 tc + malformed cx: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
82: 201 tc + zero cx: status=6 EXR_LIMIT message='PPTX table row cells exceed 200'
84: table CJK: four distinct glyph masks, pixels=1181, bbox=(50, 49, 158, 75); exact M4 text-shape raster match
441: 48pt empty paragraph/soft line 'A\r\rB': visible gap=224px, expected=224px
441: 48pt empty paragraph/soft line 'A\x0b\x0bB': visible gap=224px, expected=224px
441: 48pt leading empty paragraph/soft line '\rA': top offset=112px, expected=112px
441: 48pt leading empty paragraph/soft line '\x0bA': top offset=112px, expected=112px
441: 48pt underlined empty paragraph/soft lines '\r': ink_pixels=0
441: 48pt underlined empty paragraph/soft lines '\x0b': ink_pixels=0
441: native-ppt-text-spacing: 9 checks passed
443: MainMaster level0, prior-level size=None: matching Environment inheritance -> 12pt/alignment0, exact explicit-style raster match
443: MainMaster level1, prior-level size=None: matching Environment inheritance -> 48pt/alignment2, exact explicit-style raster match
443: MainMaster level0, prior-level size=36: matching Environment inheritance -> 36pt/alignment0, exact explicit-style raster match
443: MainMaster level1, prior-level size=36: matching Environment inheritance -> 48pt/alignment2, exact explicit-style raster match
443: native-ppt-text-master: 12 checks passed
100% tests passed out of 19
```

首轮全量测试 580/581，通过外部环境 `PYTHONUTF8=1` 修正已有测试 native-docx-edit-e5 的默认 cp1252 解码问题后完整重跑；未修改该测试或 tests/check_reading_release.py。首轮完整输出：[`ctest-default-encoding.txt`](ctest-default-encoding.txt)。

最终完整重跑命令及实际结果：

```powershell
$env:PYTHONUTF8 = '1'
ctest --test-dir build/salvage -E '^(sdk-release|sdk-doc-coverage)$' --output-on-failure --parallel 4
```

```text
581/581 Test  #91: native-ppt-real-matrix .............................   Passed    6.86 sec

100% tests passed out of 581

Total Test time (real) = 142.76 sec
ctest exit=0
```

完整输出：[`ctest.txt`](ctest.txt)。仅排除指定的 sdk-release 和 sdk-doc-coverage；prepush 仍执行了 check_sdk_docs.py。


最终 prepush 命令使用 harness 中真实脚本（此仓库 ops 目录没有该脚本），未传 SkipDocs：

```powershell
& <verification-workspace>/ops/prepush-check.ps1 -Worktree <workspaces>/EXReader-salvage-main-20261114
```

```text
ok    无冲突标记残留
ok    code/docs 结构扫描
ok    check_sdk_docs.py

全部通过 —— 可以推
prepush exit=0
```

完整输出：[`prepush.txt`](prepush.txt)。


