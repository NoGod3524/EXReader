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
首轮没有覆盖的20项会话故障和真实进程恢复，现已由下述同源候选补齐。
正式Apple账号界面、真机及六目标联合验收继续独立跟踪。

## 会话生命周期与真实进程恢复

后续候选仍从安装后的同份模块消费，原38会话和18捕获先实际重跑。
原 `tests/reader_session/check_session.py` 的20项保持原断言和时限，以iOS arm64消费者执行：
控制程序通过 `simctl spawn` 保留stdin/stdout协议，实际SDK会话入口在其后台owner线程运行，
另一个同源iOS修订消费者负责原始本地修订输入。此部分是Simulator原生worker出口，不声称它是UIKit账号界面。

同次UIKit探针另外进入交互控制模式：主线程保持窗口和活跃采样，后台owner复用原消费者。
测试在实际不可变PUT提交、GET验证被阻塞且outbox尚未ack时，对真实app PID发送SIGKILL；
重新启动同一安装包、同一账号和同一产品库，核对不可变重试412、GET验证、仅一次ack与保留历史。
还核对传输中非阻塞close、主线程采样持续、CLOSED之后才destroy。
受测源码 `4ac393384552755583d9c144ed87ed7c0aca8188` 的
[run 40080841137](https://github.com/NoGod3524/EXReader/actions/runs/40080841137) attempt1
已完整通过：producer `120833889747` 与严格证据作业 `120836676831` 均 success。
同次原38会话、18捕获、四格式原件、20项原故障断言及7项真实UIKit恢复全部通过，
UIKit实际启动3个进程，主线程在原书/阅读会话阶段记录2553次活跃采样。

`c51e772c` / run `40079854212` 已保留为失败：同次38会话与18捕获重跑通过，
原20项前9项通过后，revision输入适配失败，UIKit终止恢复未运行。
原checker会解析消费程序的软链，导致基于软链名选择角色的适配跑错程序。
现改为独立显式revision入口并在阅读套件前先做真实安装后修订消费者预检。
同时新增同源严格汇总，在Actions实际重新散列唯一producer ZIP，核38会话、20具名故障、
7项UIKit恢复、实际三份Mach-O及运行身份，并拒绝6种被修改的证据；本轮全部通过。

producer ZIP工件 `12554938471` 为14,070,562字节，
SHA-256 `c393495e3bf144719969eafdf2c092eac8d2cca0f99664cb1f79d198733065ed`，
有效期为2027-01-22T09:09:32Z；严格作业在Actions实际重新下载并计算摘要。
严格汇总工件 `12556000311` 为757字节，摘要与两作业身份完整登记在验收JSON。
本地仅编辑源码/文档与Git，未下载工件或执行构建、语法检查、测试。

正式SwiftUI账号、后台挂起/执行与scenePhase关闭、Keychain恢复界面、iPad、
真机及六目标联合验收尚未授予；本轮UIKit窗口承担前台控制与活跃观测。
