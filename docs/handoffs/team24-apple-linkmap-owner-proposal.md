# 共享链接检查器修复提案（尚未应用）

触发：第 3 轮 source `02dbb1a7cb0fa80920ad89dcdeec76bf3af5c6b0`，run `40280431991` / attempt 1，Mac job `121433503530`。

实际程序已链接：8241064 字节，SHA-256 `69004589efd300704e5aa93112dffd100438028ed1aebf7ce98ab8504dda2b58`。原 embed 检查阶段在 `tools/check_apple_product.py:30` 的 `Path(link_map).read_text()` 因原 map 的非 UTF-8 字节失败，位置 2259028–2259029。尚未启动 UI；不称可启动验收通过。

建议改动只涉及 map 的文本解码，原始 map 文件、哈希、符号/SQLite/动态 SDK 门禁和七个原负向检查全部不变：

```diff
--- a/tools/check_apple_product.py
+++ b/tools/check_apple_product.py
@@
-    mapping = Path(link_map).read_text()
+    mapping = Path(link_map).read_text(errors='surrogateescape')
--- a/tests/reader_team24_apple/run_ui.py
+++ b/tests/reader_team24_apple/run_ui.py
@@
-                deps = subprocess.check_output(['otool', '-L', binary], text=True); symbols = subprocess.check_output(['nm', '-g', binary], text=True); link = mapping.read_text()
+                deps = subprocess.check_output(['otool', '-L', binary], text=True); symbols = subprocess.check_output(['nm', '-g', binary], text=True); link = mapping.read_text(errors='surrogateescape')
```

本队 guard 仍冻结所有原工具。若获准接入上述共享 owner 修复，只为 `tools/check_apple_product.py` 钉住 seed 原文加这一处替换；其余原工具、SDK、预算和原断言继续逐字冻结。

需要在 Actions 内再次构建并执行原生 UI，不能由该解码修复推断启动或业务成功。本提案没有修改共享工具，也没有启动新的完整轮次。
