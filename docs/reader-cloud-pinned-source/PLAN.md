# 云端导入的同一文件读取候选

起点 d263ce5228838ac90c0a0dc13a5193d4a7739681。只有 cloud-import 实现、新普通回归入口和本文改变；冻结 SDK、sideload、WebDAV、旧测试、预算均不改。

第二阶段只打开一次待验证文件，SHA校验与非PDF导入共享该FILE；不再在两者之间重开stage路径。POSIX拒绝叶节点symlink且要求regular file，PDF元数据和原件经本进程仍持有的/dev/fd（Apple）或/proc/self/fd（Linux）读取。Windows只读打开不共享write/delete，并逐个持有拒绝reparse的父目录，保证SDK的PDF路径打开期间父目录不会改名；文件与目录持有持续到SDK返回。API结构、32/128MiB限制、64KiB流式缓冲、取消和提交边界不变。

这个候选不是此前被阻断的D13竞态实验，不重试、不改写该实验，也不以更换执行器绕过。没有新的并发路径替换、reparse/junction攻击或canary。云端只重放仓库原有普通HTTPS导入/九格式/独立SDK原件读回、取消、静态两阶段间损坏/删除、内存与清理错误回归；旧测试保持原字节。SDK3.40三桌面及显式3.41 Linux分别运行，不拼不同源码授予。

仍未解决：清理按stage路径执行，没有原子compare-and-unlink保障，仍要求宿主控制且稳定的私有目录。初次下载返回到SHA首次读取的身份传递也未由新API覆盖。普通回归成功不能证明并发攻击安全，D13保持未验收。Windows本候选只接受可逐组件持有的本地盘绝对规范路径，不支持UNC/设备命名空间暂存。Apple/Android/iOS的描述符路径能力按实际平台结果分别授予；本轮没有移动端授予。

旧消费者在云端复制后仅投影两处入口：CMake精确SDK请求按profile取3.40/3.41；allocator supplemental probe的相对include改为本候选cloud_import.c绝对路径，避免其通过安装include目录偶然找到另一份旧源码。原业务断言、分配失败hook及正常安装消费者不变，原文件未修改。

所有构建、语法检查、夹具、测试、工件处理仅Actions。本地仅源码/文档/Git；本候选不提升BASE、不改默认分支、不发tag/Release。旧失败保留，首轮出错后先定位，最多三轮完整回归。

第一轮639ba806/run40272739629：Windows3.40、Linux3.40及3.41原普通回归通过；macOS在编译时因严格POSIX feature选项隐藏O_NOFOLLOW而失败，尚未运行该平台业务，整体未通过。后续明确启用Darwin feature声明，POSIX初始打开加O_NONBLOCK避免非regular候选在fstat前阻塞；不增加路径替换实验，不修改旧业务断言。

## 实际普通回归结果

受测源码 `3584390d4c8fb9469e4c1795e52737b73688acfe`；run `40273482304` / attempt `1`，四producer和原ZIP认证job全部success。四profile各47项原普通业务检查通过；对应job为Linux3.40 `121411178556`、Windows3.40 `121411178718`、macOS3.40 `121411178814`、Linux3.41 `121411178846`，认证job `121412738356`。认证实际下载四ZIP并核对API大小/digest/有效期、原report必需名单、三个实际程序及每个工件成员hash，调用原report负例自检。

| profile | artifact ID | ZIP bytes | SHA-256 |
| --- | --- | ---: | --- |
| Windows3.40 | 12629900797 | 8781429 | a64cd971efaf72bd04e10e13d431d026fe14b29d2be16854dac85ee3828198ad |
| Linux3.40 | 12628744435 | 12468851 | cee64fa63c94b41281f634c8837900c49f1877bcdf5dceca1a6ed804a63ddbaf |
| Linux3.41 | 12629157189 | 12468870 | a5e005664a1031096136e3cbe4d775a9d4fd28ce5d650a1d993a17960267ac6d |
| macOS3.40 | 12628084991 | 10700849 | f879ecacbe44c9b475b21d60269d8fa79cea29c0b9316c852a93c229ed2eec5b |
| summary | 12629670721 | 734 | 91410064208b9fa023ead326b22eff882b227ec5749ae113ef45e1246100b16a |

工件有效期 `2027-01-24T05:18:11Z`。授予仅普通桌面包接口回归；路径替换实验仍未执行、D13仍未验收，清理及初次捕获身份缺口仍保留。这个文档更新不改变受测源码、不重建或发布产品。完整回归使用2/3轮，没有启动第三轮。
