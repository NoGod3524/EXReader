# Handoff：真实WebDAV服务互操作

先读[共同约束](README.md)。从固定起点新建 `codex/reader-webdav-interop`。

## 要交付的能力

已有WebDAV与sync模块在自有TLS夹具上通过；本包验证它们能否与成熟标准服务互操作。
消费安装后的 `EXReaderWebDAV`、`EXReaderRevisions`、`EXReaderSync` 和唯一产品SQLite，
不重新实现客户端或同步协议，不改现有模块代码、宿主、schema与wire。

只新增 `tests/reader_webdav_interop/**`、`tools/check_reader_webdav_interop.py`、
`.github/workflows/reader-webdav-interop.yml`、`docs/READER-WEBDAV-INTEROP.md`及本包JSON。

## 场景

在Actions内部使用固定版本／镜像digest的真实服务，例如Nextcloud/SabreDAV与Apache mod_dav。
生成临时TLS证书和测试账号，实际启用证书与hostname验证；不使用用户云盘或公开可写服务器。
至少两类真实服务，两个独立产品库与私有原件目录。

覆盖目录发现、UTF-8／空格／百分号路径、深度限制、MKCOL、条件PUT与已存在内容，
两端上传／发现／字节校验／ack、离线失败与恢复、并发头与墓碑保留、取消、重新运行幂等，
以及超过分片／载荷限额的明确拒绝。服务差异须关联实际HTTP记录，不能只断言客户端返回0。
原件散列／长度、revision原字节、history／outbox变化须由独立期望核对。

真实服务启动和所有原件生成、传输、验证都在云端；服务只在作业内运行并在结束清理。
不新建应用UI，不把本包称为真实用户云盘或六平台客户端验收。

## 交付

每类服务分别报告服务／镜像版本、源码／run／attempt、TLS身份、实际检查和保留原始日志。
保留失败，测试密码与Authorization不得出现在日志、同步payload或工件中。
若发现客户端缺陷，交最小可复现用例、真实服务证据和拟改共享文件，先由root协调源码所有权。
不得为通过而忽略条件写入、改成不校验证书、放大原有限额或跳过失败场景。

本包的结论是具体服务／声明场景的互操作结果，不继承原TLS夹具的其他平台结论。
