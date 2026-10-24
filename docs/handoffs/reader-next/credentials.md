# Handoff：平台安全凭据存储

先读[共同约束](README.md)。从固定起点新建 `codex/reader-credentials`。

## 要交付的能力

给应用账号设置提供安全保存、读取、更新、删除秘密的独立可选模块。
首版一个WebDAV账号；接口仍以调用者给定的稳定account ID区分，避免把URL规范化放进存储层。
秘密可包含用户名／密码或token，作为有界不透明字节保存，不进入产品书库、同步wire或日志。

新增目录 `extras/credentials/**`、`tests/reader_credentials/**`、
`.github/workflows/reader-credentials.yml`、`docs/READER-CREDENTIALS.md`和本包验收JSON。
不改任何宿主、SDK、产品SQL、同步模块或现有工作流。

## 平台与接口

- Windows：Credential Manager。
- macOS/iPhone/iPad：Keychain；相同语义，原生Security框架。
- Linux：Secret Service/libsecret；系统服务不可用或锁定时明确UNAVAILABLE。
- Android：Keystore保护的加密存储；使用平台AES-GCM等标准能力，禁止自定义密码学。

先写小而明确的C ABI契约；Android可另附Java入口与JNI适配，不能要求修改冻结SDK绑定。
必须区分OK、NOT_FOUND、UNAVAILABLE、ARGUMENT与IO；明确输出缓冲区所有权及大小上限。
account ID使用稳定小写UUID，服务namespace隔离。不得使用全局单例凭据或把其他应用记录列出。
平台无法安全持久化时返回UNAVAILABLE，由宿主选择仅当前会话保存，禁止自动降级明文。

模块独立CMake／Android library构建、独立版本化，默认reading-core/library构建不加入它。
主界面、账号对话框、同步调度均由root接入，不在本包修改。

## 云端出口

实际原生API验证：空存储、写入／回读、精确更新、隔离账号与namespace、删除／重复删除、
Unicode秘密、越界输入、服务不可用／锁定、错误不得泄漏秘密、重新打开后读取。
Windows/Linux/macOS须有实际运行；iOS/Android至少完成独立包与模拟器调用验证后才授予对应平台。
未运行的平台逐项标pending，不用桌面结果替代。

使用作业内随机生成的测试秘密和专用临时存储／测试namespace；清理只涉及自己的记录。
Linux测试服务仅在Actions作业内运行，macOS测试keychain与Android测试应用均独立，
不能访问开发者真实keychain、账号或云盘。报告不打印秘密，原始日志也不得包含秘密。
没有平台运行证据时不得把占位实现列为完成。

交付installed消费者、原始日志与同源报告；根目录构建、UI、真机和账号同步验收由后续包负责。
