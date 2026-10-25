# Dot 七包：共同执行约束

本批由用户要求挑选，交给 Dot 协调。七包已有实际远端分支和运行；最近核对六包success、Windows导入整理仍在运行，见INDEX。旧“尚未派发”记录不再适用；root没有通过接口发过消息，但不能由此推断用户未手动派发。保留原writer，不将这些包再次交给其它会话从头实施。

仓库：https://github.com/NoGod3524/EXReader 。总体目标仍是原生六目标阅读器（Windows/macOS/Linux/Android/iPhone/iPad）、用户自有云盘/WebDAV、本地和电脑导入、书架分类系列、进度/书签/标注/搜索/设置，默认界面简洁。本批负责有限范围，最终共同验收仍归 root。

## 起点和写入者

每包任务书有完整固定起点和独占分支。新建独立 clone/worktree，从该 SHA 开始；不改原交付工作树，不 reset/切换用户已有树，不追移动主线。共享任务说明不必在实现起点树里，用本目录固定提交的URL读取。原任务模板的初始 f43 起点被本轮任务书的交回HEAD替代；冻结项与原路径归属继续适用。

当前 root 三个主线 owner：Android 正在修 J04 并准备正式宿主文件入口；GTK 正在接 J03 拖放/文件剪贴板并补 folder owner；Apple 正在收 records UI 与原回归。不得修改 examples/android、examples/linux、Apple正式宿主或它们的已有测试。T01独占本批 Windows 正式接线，T05仅新增组合验证，其余五包只在各自原包内部复审。

## 固定约束

- SDK固定 9854061be331fe603a1822d9b2b36ee357154927，3.40.0/ABI1。src、include、cmake、顶层CMakeLists.txt、tests/fixtures、bindings、native.yml、reliability.yml逐字不改；产品schema1、wire、anchor、CPU基线与预算不改。
- 所有构建、测试、语法检查、夹具、服务、benchmark、工件下载/解包/解析只在 GitHub Actions。本地（含工作代理的执行主机）只做源码/文档/Git，不能先运行一次parse或编译再披露。
- 可提交/push本包功能分支并自行触发、查看、修复Actions；不需再询问是否push。不得推默认分支、合PR、签名、tag/Release或改变保护规则。不要创建未经要求的外部消息/issue评论。
- 复用安装后的公开模块，不写SDK私有SQL，不新增第二套SQLite/wire/网络后端、WebView、常驻服务或动态插件框架。
- 先定向阅读本包实现、调用者、公共头、真实消费者、原云端证据和汇总器。发现问题按根因最小修；不为增加工作量重写已通过模块。没有源码缺陷时做有证据的复核记录，不为纯文档变更重开昂贵完整运行。
- 原断言、失败、语料、历史工件保留；不能删除真实失败、放宽计数/限额、把实际缺陷改成预期拒绝。新源码必须有它自己的真实验收，不能继承旧SHA绿灯。

## 每包云端出口

HEAD==GITHUB_SHA、固定起点祖先、冻结树/产品schema相等、路径白名单；新模块先安装，再由独立C/C++消费者消费（平台包用实际独立probe）。保留原具名用例与有意义的错线程、重入、取消、寿命、错误/原子性回归。

汇总必须认证实际同source/run/attempt的completed/success上游作业，唯一工件名称/ID、非空大小、有效期、API digest；Actions内下载重算ZIP SHA与大小，拒绝重复成员/报告、缺项、错source/attempt及篡改。绑定实际消费者或宿主二进制，不只认证自报accepted。

完成后推代码和只含证据文档的 [skip ci] 提交，交回完整tested SHA、最终HEAD及两者差异、run/attempt/job、具名结果、工件ID/大小/SHA/有效期、失败记录、剩余缺口。只按实际桌面/模拟器/真机、控件/性能/读屏范围分别授予。由root做最终共同集成，Dot不要合回主线或自行增加下一批包。
