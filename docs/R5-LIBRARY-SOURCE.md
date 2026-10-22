# R5：书库原件随机源

本阶段新增 `exr_library_source(library, book_id, &source, &error)`，供宿主将原件交给已有
`exr_publication_open_source()`。书库只导出原件字节，不调用 layout 层、不解析 EPUB，也不复制整本到堆。

成功返回的 source 由调用者负责 `source.release(source.context)`；reader 成功接收后才转移所有权，
打开失败仍由调用者释放。source 保留内部书库引用，因此 `exr_library_close()` 之后仍能读，包括 `:memory:`。
最后一个 source 释放才实际关闭数据库。原 blob/完整文档快照 API 语义不变。

每次读只持有临时 SQLite blob cursor，调用结束就关闭；同 owner 的标题、封面和进度更新不会使后续读失效。
owner 成功删除书籍会永久使该书的旧 source 失效，即使之后重用 ID 也不会读入新书。
每次读前后核对 `PRAGMA data_version`，其他数据库连接的任意提交均保守地使 source 永久失效。
此时 reader 报读取失败，宿主应重新打开 source/reader 并重新解析位置，不能猜测旧位置仍有效。

此阶段不修改 schema6 或旧全书偏移含义，不扩大 EPUB 导入上限，不代表所有宿主已采用有界路径。
章节位置持久化、有界 EPUB 导入及平台接入是后续阶段。直接修改数据库文件或绕过 SDK 改 owner 的原件不在契约内。

云端验证包含文件库和内存库、随机字节比较、关闭次序、owner 更新、删除/ID 重用、跨连接失效、
错误清理，以及存储原件经 publication 到 bounded pager 的真实绘制/选文/锚点路径。
内部测试额外注入非法 SQLite 存储；安装后消费者只使用公开头及静态组件。
执行 `.github/workflows/bounded-library.yml` 的普通与 ASan/UBSan 作业，并对相同源码运行完整 native 工作流。
结果需以实际运行登记，未运行或未通过不得记为完成。
