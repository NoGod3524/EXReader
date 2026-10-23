# 原生 HTTPS WebDAV 书籍来源

`extras/webdav`是独立、可选的静态模块，公开 C 接口、内部使用 C++17。
宿主可列举用户指定的 WebDAV 目录，并按需把文件下载到自己的私有目录。
它不进入默认 SDK，不改冻结 SDK `9854061be331fe603a1822d9b2b36ee357154927`、
SDK 3.40.0／ABI 1／schema 7 或产品 metadata schema。

现有产品契约把 WebDAV 路径、TLS、凭据及同步协议留给宿主，尚未固定 revision wire。
本模块只实现只读来源；远端写入、原书上传、revision/outbox、并发冲突及删除墓碑仍属 P3。

## 安装和宿主接入

Windows 使用 WinHTTP、XmlLite 和系统证书信任，不带浏览器或额外 TLS DLL。
Linux 使用系统 libcurl 与 libxml2，需要对应开发包；其 TLS 后端、共享库和许可证随宿主发行。
本包不改变这些库的配置或全局证书校验策略。

```text
cmake -S extras/webdav -B build/webdav -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=<module-prefix>
cmake --build build/webdav
cmake --install build/webdav
```

消费者启用 C++17 编译器，将模块前缀加入 `CMAKE_PREFIX_PATH`，使用
`find_package(EXReaderWebDAV CONFIG REQUIRED)` 和 `EXReaderWebDAV::exr_webdav`。
公开头只有 `exr_webdav.h`，不借用 SDK 私有结构。

宿主在自己的网络 worker 上调用 `exr_webdav_list`，保存返回的 `resource`；
用户选择文件后调用 `exr_webdav_download_file`，为目标指定稳定私有目录和一个普通文件名。
原书发布成功后，再把文件送入现有 `exr_sideload_import_file`，并在 SDK owner 队列完成导入。
来源模块不打开书库，不越过既有导入与 metadata 接受边界，也不新增假 UI 按钮。

## 限额和路径

- 目录只发 `Depth: 1`，最多 4 MiB XML、20,000 元素、32 层和 2,000 个子项；调用者可降低限制。
- 文件以最多 64 KiB 的应用缓冲写入，最多 128 MiB；不分配整本原书。TLS／系统缓冲另由原生库管理。
- 根 URL 必须为 HTTPS 集合并以 `/` 结尾。首版支持 DNS／IPv4，不支持 IPv6 字面量。
- 资源使用根目录内的 URI 路径，拒绝 userinfo、query、fragment、点段、重复分隔、编码分隔符、双重编码和控制字符。
- DAV XML 通过原生 namespace parser 读取；拒绝 DTD、外部实体、越出根目录或 Depth 的 href、重复项及缺失必需属性。
- 首版接受一个成功 `propstat`，可同时存在未成功的其他 `propstat`；多个成功属性组返回可重试的格式错误。

资源标题只用于显示。远端路径、标题与 ETag 都不用于拼接本机目标文件名。
本机文件名拒绝目录分隔符、流名、设备名及跨平台非法字符；同名目标始终保留。

## HTTPS、凭据和失败恢复

一个 client 对应一个 HTTPS origin 和根集合。Authorization 从配置复制，只在该 client 的会话内保存；
宿主从平台安全存储或当前会话提供它。本模块不管理长期凭据，也不把它写进日志、文件或产品数据库。
不使用系统隐式认证、cookie 或代理环境变量。

重定向由模块逐次检查，最多四次，只接受同 origin 且同根目录内的 HTTPS 路径。
跨源跳转在发出下一请求前拒绝；远端错误不触发凭据转发或删除本机书籍。
默认启用系统证书和 hostname 验证，没有关闭验证的模块选项。

下载使用同目录临时文件；失败、取消、超额或传输截断会清理临时文件。
Linux 用目录句柄和 `linkat`、Windows 用不覆盖的 `MoveFileExW` 原子发布。
调用者须保证私有目录在调用期间稳定、由本应用控制；模块拒绝直接 symlink/reparse 目录。
已经存在的文件或链接不会被覆盖。发布一旦提交，结果仍是成功，不因随后到达的取消而删除原件。

接口同步运行，取消在 I/O 和发布边界检查。正在阻塞的系统调用受到剩余 timeout 限制，
Windows 的多个系统阶段可能依次消耗该等待额度；不声称立即中断或硬实时截止。
401 返回需要凭据，其他 HTTP 错误、TLS／网络错误及限额失败均可由宿主重试；client 不会因此失效。

## 云端验收状态

首个候选 `809246e500cff9714f15a4f489f7594dda480604` 的 run `40030890464`
在编译阶段拒绝：Linux 的严格诊断发现同行条件语句缩进，Windows 缺少 COM 头的显式前置包含。
修复保留严格编译标志，提交 `341c3f17`。第二轮 run `40031024147` 的 Linux 67 项通过；
Windows 已编译并安装，但 runner 的混合 PowerShell module path 导致证书 provider 不可用，尚未进入 HTTPS 用例。
后继只改测试服务的证书安装方式为系统 `certutil`，不放宽 TLS 校验；两平台最终同源验收尚待完成。

`.github/workflows/reader-webdav.yml`在 Windows 和 Linux 独立安装模块，再仅从安装目录编译消费者。
云端测试服务生成临时 CA 并加入 runner 信任库，真实完成原生 TLS 握手，另外验证不可信证书和 hostname 拒绝。
逐项检查 Depth:1、namespace、流式字节、取消、限额、截断、HTTP 错误恢复、路径拒绝、凭据隔离及不覆盖发布。
原始结果与请求记录保存在同次源码工件内；本地不构建、不起服务、不生成夹具、不下载或解析工件。

本交付不授予跨设备同步、移动平台适配、系统凭据存储、宿主导入 UI 或产品完成结论。
