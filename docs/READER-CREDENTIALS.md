# 平台安全凭据存储

`extras/credentials`是独立、可选的静态模块（C11），给应用账号设置提供
保存、读取、更新、删除秘密的统一 C ABI。首版服务一个 WebDAV 账号，但接口只按
调用者给定的稳定 account ID 区分记录，不解析 URL，也不做 URL 规范化。
它不进入默认 SDK／reading-core 构建，不改冻结 SDK `9854061be331fe603a1822d9b2b36ee357154927`、
产品 SQL、同步 wire、宿主或现有工作流；主界面、账号对话框和同步调度由 root 接入。

## C ABI 契约

公开头 `exr_credentials.h`，版本 `EXR_CREDENTIALS_VERSION "0.1.0"`，CMake 包
`EXReaderCredentials 0.1.0`（SameMajorVersion），目标 `EXReaderCredentials::exr_credentials`。

```c
exr_credentials_status exr_credentials_open(const char *service_namespace, exr_credentials_store **);
void exr_credentials_close(exr_credentials_store *);
exr_credentials_status exr_credentials_put(store, account_id, const uint8_t *secret, size_t length);
exr_credentials_status exr_credentials_get(store, account_id, uint8_t *buffer, size_t capacity, size_t *out_length);
exr_credentials_status exr_credentials_delete(store, account_id);
const char *exr_credentials_status_name(exr_credentials_status);
void exr_credentials_wipe(void *, size_t);
```

| 状态 | 值 | 含义 |
| --- | ---: | --- |
| `EXR_CRED_OK` | 0 | 成功 |
| `EXR_CRED_NOT_FOUND` | 1 | 该 namespace／account 无记录；删除不存在的记录也返回它 |
| `EXR_CRED_UNAVAILABLE` | 2 | 安全存储不存在、被锁定或拒绝访问；未写任何明文 |
| `EXR_CRED_ARGUMENT` | 3 | namespace／account／长度／指针非法，或输出缓冲区不足；存储未改变 |
| `EXR_CRED_IO` | 4 | 平台存储失败或记录损坏（含 Android 密文被调换或篡改） |

- **namespace**：1–64 字节 `[a-z0-9.-]`，首字符 `[a-z0-9]`，每个应用／服务一个，如
  `org.exreader.reader.webdav`。所有记录以 (namespace, account) 为键。
- **account ID**：调用者的稳定小写规范 UUID，恰好 36 字节；大写、花括号、无连字符等一律 ARGUMENT。
- **秘密**：1–2048 字节不透明字节（`EXR_CREDENTIALS_SECRET_MAX`），可放用户名／密码或 token，
  允许 NUL 和任意 UTF-8；上限适配所有后端（Windows 记录 blob 最多 2560 字节）。
- **所有权**：`open` 分配句柄，`close` 释放；输入秘密只在调用期间借用；输出写入调用者缓冲区，
  模块从不为调用者分配输出。`*out_length` 总被写入：OK 时为长度；缓冲区不足时返回 ARGUMENT、
  写入所需长度且缓冲区不动；其他失败为 0。2048 字节缓冲区总是足够。用完用 `exr_credentials_wipe` 清零。
- `open` 只校验并分配，不连接系统服务。句柄可跨线程共享；同一账号并发写为后写者生效。
- 状态没有消息字符串，失败路径无法回显秘密。模块源码不含任何打印或日志调用（云端静态检查）。
- 模块从不枚举记录、不列出其他应用的记录，不持有进程级凭据单例。
- **无法安全持久化时返回 UNAVAILABLE，绝不降级为明文**。是否改为仅当前会话保存由宿主决定。

## 平台后端

| 平台 | 原生存储 | 记录键 | UNAVAILABLE |
| --- | --- | --- | --- |
| Windows | Credential Manager `CredWriteW/CredReadW/CredDeleteW`，`CRED_TYPE_GENERIC`，`CRED_PERSIST_LOCAL_MACHINE`（本机当前用户，不漫游） | target `EXReaderCredentials/<namespace>/<account>` | 无凭据登录会话（服务、S4U 任务）、拒绝访问、策略禁用 |
| macOS | Security.framework `SecItem*`，`kSecClassGenericPassword`，用户默认 keychain 搜索列表 | service `EXReaderCredentials/<namespace>` + account | keychain 锁定（禁止交互，不弹解锁框）、无默认 keychain、缺授权 |
| iOS/iPadOS | 同上，应用 data protection keychain，`AfterFirstUnlockThisDeviceOnly`，不同步 | 同上 | 首次解锁前、缺 entitlement |
| Linux | Secret Service（libsecret ≥0.19，`secret_service_*`），默认 collection，schema `org.exreader.Credentials` | 精确属性 `namespace` + `account` | 无会话总线／服务、无默认 collection、collection 或条目锁定；从不解锁、不弹提示 |
| Android | Java `CredentialStore`：每 namespace 一把不可导出 AndroidKeyStore AES-256 key；每 account 一份 AES-GCM 记录（平台随机 IV，AAD 绑定 namespace+account），存于 no-backup 私有目录，原子替换 | 文件 `<noBackup>/exreader-credentials/<namespace>/<account>.rec` | Keystore 不可用；C ABI 未绑定 Java 时 |

Android 的 C ABI 由 `src/android.c` 经 JNI 调用 Java 库中的 `CredentialStore` 桥方法；宿主在自己的
JNI 入口调用一次 `exr_credentials_android_initialize(env, context)`（头 `exr_credentials_android.h`），
不修改冻结 SDK 绑定。只用平台 JCA 的 AES/GCM，无自定义密码学；记录被调换到其他账号或 namespace 时
GCM 认证失败返回 IO，而不会读出他人秘密。

## 构建与接入

```text
cmake -S extras/credentials -B build/credentials -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=<prefix>
cmake --build build/credentials
cmake --install build/credentials
```

消费者 `find_package(EXReaderCredentials 0.1 CONFIG REQUIRED)` 并链接
`EXReaderCredentials::exr_credentials`。Linux 需 `libsecret-1` 开发包及运行时 Secret Service
（如 gnome-keyring、KWallet）；Windows 链接 `advapi32`；Apple 链接 Security/CoreFoundation。
Android：以 NDK toolchain 构建并安装同一 CMake 包，另以 `gradle -p extras/credentials/android
:credentials:assembleRelease` 产出 Java 库 AAR（含桥方法 keep 规则），两者一起打包进宿主。
iOS 与 Android 发行应用须使用自己的签名、keychain access group／应用身份。

建议接入：宿主为 WebDAV 账号生成并保存一个 UUID；保存时以 `org.exreader.reader.webdav`
namespace 写入凭据（如 `user\0password` 或 token 的序列化字节），连接时读出并只交给
`exr_webdav_config.authorization` 等内存配置，然后清零。凭据不写入产品书库、同步 wire 或日志。

## 云端验收

工作流 `.github/workflows/reader-credentials.yml`，所有构建、测试和工件解析均在 Actions：

- 每个作业先验证受测 SHA 继承固定起点 `210403d121d6484a8fff4ea7ffd911efa3163535`、冻结 SDK 未变、
  变更仅限本包路径、模块源码无日志调用、默认构建未引用本模块。
- 桌面作业构建并安装模块，再以仅依赖安装包的独立消费者运行实际原生 API；iOS 在新建的模拟器设备上
  运行 ad-hoc 签名探针 app；Android 在 API34 模拟器运行新安装探针，同时经 JNI 走 C ABI 与直接调用 Java API。
- 测试秘密由作业内 CSPRNG 生成，经 stdin 或用后即删的输入文件传给消费者，从不打印；
  报告前对全部输出、原始日志、安装文件和消费者二进制按原文／hex／base64 扫描，命中即拒绝。
- 隔离存储：Windows 使用随机测试 namespace 并只删除自己的记录；Linux 在作业内私有 D-Bus 与临时 HOME
  的 gnome-keyring；macOS 临时 keychain 作为唯一搜索列表和默认 keychain，结束后恢复原列表并删除；
  iOS 新建并删除模拟器设备；Android 测试 app 结束后卸载（同时删除其 Keystore key）。
- 覆盖：空存储、写入／回读、精确更新（更短值无残留）、账号与 namespace 隔离、删除／重复删除、
  Unicode 与含 NUL 的二进制秘密、最大值与越界、缓冲区不足、非法 ID／namespace／NULL、
  服务不可用／锁定、新进程重新打开后读取、仅清理自己的记录。
- `same-source report` 作业把各平台报告与本 run 的作业结论、工件 ID／字节／SHA-256 绑定；
  缺少同源已接受报告的平台保持 pending。

验收结果见下节及 [reader-credentials.json](validation/reader-credentials.json)。

## 结果

待云端运行。
