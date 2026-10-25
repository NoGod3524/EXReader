# D01：新SDK的旧阅读记录与锚点兼容出口

先读[共同约束](README.md)。固定起点a826a65c9c66e43620eff61b49cb79f941a3c953；唯一分支 **codex/dot-sdk-record-migration**。

## 具体问题

部分宿主用exr_version组成parser_version/source身份。3.41虽然只新增canvas背景入口，旧3.40保存的阅读记录能否安全重开尚无证据。不能用两个版本各自新建记录通过来回答旧记录迁移，也不能偷偷把3.41的身份伪装成3.40。

Actions可分别git archive并构建：旧SDK9854061be331fe603a1822d9b2b36ee357154927、新SDK生产源码edddc463c06ed5731195cdb8f06b2df6dff7699e。模块显式版本选择可普通merge **f680aeaddfb1ecc67ead353554f5b91a5703f72f**（已测实现，run40166479919）；该交付只允许其原版本声明/工具变化，模块实现仍保持固定。记录合并后的基点并守卫。

## 必须交付

1. 老版本真实进程打开/导入TXT、EPUB全局/有界章节、PDF、CBZ，调用公开capture以及G03真实命令生成进度、书签、范围标注、笔记、删除/restore和已有wire v1/v2记录；固定原件字节/SDK id仅作本机参考，跨版本身份仍用书籍原始hash/公开结构。
2. 关闭全部句柄后用新SDK真实新进程重开同份原件/公开库与产品记录，逐项decode、分类和公开resolve；再反向读取新版本生成记录，形成3.40→3.41、3.41→3.40双向矩阵。记录parser tag、原始wire字节/散列、FOUND/MISSING/AMBIGUOUS/LEGACY/拒绝及真实定位文本/part/page，不能只看返回码。
3. 无变更原件先验证原偏移/quote/上下文不走样；错误书籍、缺spine、不同内容、坏wire/未知版本、冲突/墓碑均安全拒绝，不自动跳页、不覆写或删除旧记录。不以回退到百分比或同名书掩盖失败。
4. 原SDK保护树、原件、SDK notes/进度、产品history/outbox在只读迁移probe前后保持不变。两个版本分别安装消费，依赖与实际程序身份单独认证。

先执行Windows/Linux，macOS可增测。若按现行规则安全拒绝旧parser标签，兼容报告可以完成，但 **migration_accepted必须false**，保留缺口及公开接口层面最小方案，交root处理；本包不能改SDK、reading-state/commands模块、wire/source规则或预算。

## 唯一写入范围

- tests/reader_sdk_record_migration/**
- .github/workflows/reader-sdk-record-migration.yml
- docs/READER-SDK-RECORD-MIGRATION.md
- docs/validation/reader-sdk-record-migration.json

现有模块、消费者和宿主一字不改。最终报告区别测试工具通过、旧库真实兼容、跨设备同步和完整产品。
