# J03 root复核：原生剪贴板对象的内存边界

受检HEAD `c75076497b7e37f535ec15222b4775b85daa3419`，实现受测SHA `f2c95f9a4cc013f294edc55fefe12b8da3d5a5a5`；HEAD只增两份证据文档。旧run `40123821461` 保留，root尚未授予共同源码集成。

## 合入前必须补齐

`extras/desktop-drop/src/windows.c` 的 `request_from_unicode_text()` 在 `GlobalLock()` 后直接用固定1 MiB预算进行 `wcsnlen()`，没有用 `GlobalSize()` 限定实际HGLOBAL分配的长度；小缓冲区没有终止符时会读取分配边界之外。解析真实剪贴板/IDataObject内容时，输入预算不能替代实际缓冲区边界。

同文件 `request_from_file_group()` 在确认HGLOBAL大小之前读取 `FILEGROUPDESCRIPTORW.cItems`，再按声明数索引 `fgd[index]`。实际分配可能比结构头还小，或声明数超过实际描述符数量；256项builder上限仍不能保护第一项/前256项的越界。应先检查头部和实际可容纳数量，并以无溢出方式验证声明长度。

`exr_drop_windows_request_from_hdrop()` 同样应证明其DROPFILES输入在调用Shell解析前有完整头部、合法pFiles偏移、在实际分配内终止的单双字节列表；不能只用DragQueryFile返回的声明数量来推断源缓冲区有效。

要求原owner在同包内最小修补并补实际HGLOBAL/IDataObject负例：零/短头、无终止符、奇数字节UTF-16、cItems超实际空间/极端值、非法pFiles偏移、单双字节列表截断；保留已有真实shell、300项截断、Unicode、取消/重入、三平台安装消费者及同次ZIP认证。用ASan或等价实际内存检查证明坏缓冲区干净拒绝，不能仅比较返回码后忽略崩溃。

另有已披露的窗口销毁后再detach遗留COM引用：在接入长期运行宿主前应明确消除，或用真实生命周期证据证明无持续增长；不能把“泄漏很小”当作释放通过。

上述是源码推导，本地未执行构建/测试。已在 DeepSeek Harness 原会话“J03 desktop-drop implementation and cloud acceptance”提交返修，界面确认“进行中/正在分析请求”；保持 Flash1017 / High / PTC / 完全权限，root不并行修改其包工作树。原owner的新源码 `03babdbe2d2a608c9a2c1c280b6a238e1b99dc1f` / run `40135689234` 已提交云端验收，结果尚未授予。
