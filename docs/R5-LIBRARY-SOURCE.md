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

## 随机读第一阶段云端记录

受测源码 `a0c35f5f01ff88244470ef395886410b78293693`，run
[39857282570](https://github.com/NoGod3524/EXReader/actions/runs/39857282570)，attempt 1，普通与
ASan/UBSan 两作业均 success。每个作业原生组件测试 4/4、安装后公共消费者 5/5；
包含原件随机读、生命周期、删除重插、WAL 和 publication/pager 路径。
完整 native 同源 run `39857283787` 的结果单独核对，不能由上述两作业代替。

| 工件 | ID | 字节 | SHA-256 |
| --- | --- | --- | --- |
| bounded-library-OFF-39857282570-1 | 12460156746 | 7132189 | c0087c0882c8416b01f111e66d790af70f021d1f0f9bdfd628198a0d94026bc0 |
| bounded-library-ON-39857282570-1 | 12459603941 | 40297772 | 31ecf125467deb865ef4f5fa072a0b355d9b41c6f4977a6698bf81fdfce83fda |

两工件均绑定上述 run/source，查询时未过期，到期时间均为 `2027-01-20T21:26:33Z`。
本记录不包含后续 schema 7、有界 EPUB 导入、章内进度或标注；这些改动需新源码重新验证。
