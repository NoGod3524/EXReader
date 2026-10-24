# iOS 原生 SDK 与账号会话接续

基线为产品工作候选 `f43baf91`，冻结 SDK `9854061b` 与产品 schema 1 不变。
本包复用安装后的公开 SDK、原件导出、阅读状态、产品修订及 `reader_session`，
将已有四格式原书和18个真实捕获探针接到实际后台账号会话。

每次传递都由发送端、接收端各完成一次256分片扫描。共19次传递、38次实际会话，
涉及TXT/EPUB/PDF/CBZ原件、进度、书签和标注。原有精确字节、远端字段保留、
重复EPUB脊序路由、17 FOUND/1 AMBIGUOUS与零错位断言全部保留。

UIKit主线程仅显示测试视图并记录活跃采样；SDK调用在独立owner工作线程，
会话内部网络线程只接收产品路径和已经导出、释放SDK借用的原书文件。
每次会话必须先到CLOSED才能destroy；FINISHED不能声明书库永久完整。
Darwin链接图另核对唯一的已安装产品SQLite提供者。

构建、夹具、测试与工件处理均仅在Actions。
首轮受测源码 `88c64f51011b3bc48e1e8daf51c0058b02f756c0` 的
[run 40072678469](https://github.com/NoGod3524/EXReader/actions/runs/40072678469) attempt1
已成功，作业 `120809307986` 的全部执行步骤通过。实际 iOS26.2 arm64 iPhone16Pro Simulator
完成四格式原书、18锚点（17 FOUND/1预期歧义、零错位）、38次各256分片会话，
主线程活跃采样2046次。实际消费者为 `b4c30d1e8b013289d913bf3d14cf27d45619bfa9d305798c87429e46a2421bc6`。
单一SQLite provider、系统Foundation依赖与无SDK指针跨网络线程检查同次通过。

工件 `12552207361` 为12,435,660字节，同source/run、未过期，
API与上传日志摘要均为 `sha256:57b34561a37b1779ab66552225f6adfbdcea4dbdb24563ddac43fc7996f0472c`。
此轮未独立下载ZIP重算摘要；上述范围仅授予该次Simulator会话与原书/阅读捕获出口，
完整身份见[验收记录](validation/reader-ios-session.json)。
这一步没有接入正式Apple账号界面，也尚未覆盖原20项会话故障套件、
真实进程终止后恢复、真机或六目标联合验收；后续仍需补齐这些出口。
