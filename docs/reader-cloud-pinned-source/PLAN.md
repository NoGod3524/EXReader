# 云端导入的同一文件读取候选

起点 d263ce5228838ac90c0a0dc13a5193d4a7739681。只有 cloud-import 实现、新普通回归入口和本文改变；冻结 SDK、sideload、WebDAV、旧测试、预算均不改。

第二阶段只打开一次待验证文件，SHA校验与非PDF导入共享该FILE；不再在两者之间重开stage路径。POSIX拒绝叶节点symlink且要求regular file，PDF元数据和原件经本进程仍持有的/dev/fd（Apple）或/proc/self/fd（Linux）读取。Windows只读打开不共享write/delete，并逐个持有拒绝reparse的父目录，保证SDK的PDF路径打开期间父目录不会改名；文件与目录持有持续到SDK返回。API结构、32/128MiB限制、64KiB流式缓冲、取消和提交边界不变。

这个候选不是此前被阻断的D13竞态实验，不重试、不改写该实验，也不以更换执行器绕过。没有新的并发路径替换、reparse/junction攻击或canary。云端只重放仓库原有普通HTTPS导入/九格式/独立SDK原件读回、取消、静态两阶段间损坏/删除、内存与清理错误回归；旧测试保持原字节。SDK3.40三桌面及显式3.41 Linux分别运行，不拼不同源码授予。

仍未解决：清理按stage路径执行，没有原子compare-and-unlink保障，仍要求宿主控制且稳定的私有目录。初次下载返回到SHA首次读取的身份传递也未由新API覆盖。普通回归成功不能证明并发攻击安全，D13保持未验收。Windows本候选只接受可逐组件持有的本地盘绝对规范路径，不支持UNC/设备命名空间暂存。Apple/Android/iOS的描述符路径能力按实际平台结果分别授予；本轮没有移动端授予。

旧消费者在云端复制后仅投影两处入口：CMake精确SDK请求按profile取3.40/3.41；allocator supplemental probe的相对include改为本候选cloud_import.c绝对路径，避免其通过安装include目录偶然找到另一份旧源码。原业务断言、分配失败hook及正常安装消费者不变，原文件未修改。

所有构建、语法检查、夹具、测试、工件处理仅Actions。本地仅源码/文档/Git；本候选不提升BASE、不改默认分支、不发tag/Release。旧失败保留，首轮出错后先定位，最多三轮完整回归。
