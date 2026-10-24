# 真实WebDAV服务互操作

本包检查已交付的 `EXReaderWebDAV 0.2.0`、`EXReaderRevisions 0.3.0`、`EXReaderSync 0.1.0`
与唯一产品SQLite能否和成熟的标准WebDAV服务互操作。它不重新实现客户端或同步协议，
不修改模块代码、宿主、schema1或wire v1，也不放宽任何既有限额。

起点固定为 `210403d121d6484a8fff4ea7ffd911efa3163535`（见共同约束）。
工作流在每次运行时拒绝：非该起点后代、SDK冻结树或schema1变化、`apps/`、`extras/`及
原有WebDAV/revision/sync测试的任何差异，以及本包允许路径以外的新增文件。

## 被测服务

每类服务在 Actions 的独立 job 中运行，只监听 `127.0.0.1`，job 结束即删除容器、数据和测试信任：

| 服务 | 镜像（index digest固定） | WebDAV实现 | TLS终止 |
| --- | --- | --- | --- |
| `apache` | `httpd:2.4.68@sha256:03f858ef…0fdd` | Apache httpd `mod_dav` + `mod_dav_fs`，Basic认证 | httpd `mod_ssl` |
| `nextcloud` | `nextcloud:33.0.10-apache@sha256:e02fb1a7…13a1` | Nextcloud（SabreDAV），独立测试账号 | 镜像内Apache `mod_ssl` |

两份配置见 [services/apache/httpd.conf](../tests/reader_webdav_interop/services/apache/httpd.conf) 与
[services/nextcloud/zz-interop-tls.conf](../tests/reader_webdav_interop/services/nextcloud/zz-interop-tls.conf)。
报告逐项记录 `docker image inspect` 的RepoDigests、image ID、运行容器的image ID，以及
`httpd -v`/模块列表或 Nextcloud `occ status`、SabreDAV `Version::VERSION`、Apache与PHP版本。

每次运行在云端新生成：测试CA、服务证书（SAN仅含服务主机名）、同主机名的自签不受信证书、
随机测试密码（Nextcloud另有随机管理员密码）。CA进入系统信任库，客户端保持
libcurl `VERIFYPEER=1`、`VERIFYHOST=2`；主机名经 `/etc/hosts` 指向本机。
不使用用户云盘、公开可写服务器或真实账号秘密。

## 驱动与独立核对

[consumer/main.cpp](../tests/reader_webdav_interop/consumer/main.cpp) 只链接安装后的
`EXReaderSync::reader_sync`（传递带入 Revisions、WebDAV 与产品SQLite），调用公开C API：
`exr_webdav_list/download_file/make_collection/publish_file`、`reader_sync_step`、
`reader_revision_local/get/heads`。Authorization只经环境变量传入，不进argv或输出。

[run_interop.py](../tests/reader_webdav_interop/run_interop.py) 的期望全部独立得出：

- 原件在作业内生成，长度与SHA-256由Python计算；revision原字节由测试自己序列化。
- 服务端内容由独立的Python标准库HTTPS客户端（同样校验CA与主机名）GET/PROPFIND核对。
- history/outbox/墓碑由只读SQLite查询产品库核对，exact wire再经已安装 `reader_revision_get` 导出比较。
- 每项检查附带服务端自身access log中该检查窗口内的模块请求行（方法、原始请求行、状态、
  `Depth`、`If-None-Match`），按User-Agent排除独立客户端；断言基于这些实际HTTP记录，
  而不只是客户端返回码。access log格式不含Authorization。

[check_reader_webdav_interop.py](../tools/check_reader_webdav_interop.py) 在汇总job中经GitHub API
确认本run/attempt/source、两个服务job和工件digest，并从工件中的原始access log重新统计：
模块只用 PROPFIND/GET/PUT/MKCOL，所有PUT带 `If-None-Match: *`，所有PROPFIND为 `Depth: 1`，
至少有真实的 `PUT 412`、`MKCOL 405`、`MKCOL 409`；每项检查引用的请求行必须存在于该日志中。

## 场景（每类服务各33项）

| 组 | 检查 |
| --- | --- |
| TLS | 服务出示的证书即生成证书并经系统信任+主机名验证；不受信证书、主机名不符均在任何HTTP请求前以 `EXR_DAV_TLS` 拒绝 |
| 发现 | Depth:1 只返回直接子项；UTF-8/空格名称以规范化编码resource列出并核大小/ETag；下调条目数和列表字节上限时整体拒绝而非截断 |
| 百分号 | 含 `100%.txt` 子项的集合整体返回 `EXR_DAV_ARGUMENT`（服务端已答207）；`%25` 根URL在任何请求前拒绝 |
| MKCOL | 新建201、已存在405被接受、缺父409报告为HTTP错误 |
| 条件PUT | 首次201，相同/不同内容的再次PUT均412且服务端字节不变；预先存在的外来内容不被覆盖；超过下调下载上限的GET拒绝且不发布文件 |
| 两端交换 | A、B两个独立产品库与私有原件目录：离线history/outbox；A先发原件后发revision、每次ack前有新GET；B上传自己的原件并取得A的原件与exact wire；A取得B的；服务端对象长度/SHA/wire与产品库逐字节一致；已存在对象412后GET核对再ack；服务端原件损坏时拒绝且不ack，修复后重试成功；UTF-8+空格根目录下两端交换 |
| 并发与墓碑 | 同一tag两端并发 put 保留2个head；删除墓碑在远端与两端history中保留 |
| 限额 | 2000项分片可列出并按游标分页；2001项分片整体拒绝；列出的revision超过1 MiB在下载前拒绝 |
| 取消 | 预取消不发请求并保留outbox；上传中途取消服务端不提交、不留临时文件、不ack，并按服务端实际状态重试或保留失败 |
| 离线 | 停止服务容器时以IO失败并保留outbox；重启后同一revision只PUT一次 |
| 重跑 | 对两端已同步分片重跑只产生PROPFIND/GET，history、outbox、服务端树均不变；重放同一本地wire不重新入队 |
| 卫生 | 全部模块写入为条件写入、全部列表为Depth:1、无SQLite文件上传、至少一次真实412 |
| 凭据 | 证据、服务端日志与数据副本、产品库中无测试密码、Basic token或Authorization值 |

失败项保留在报告中（组内首个失败后其余项记为未运行；独立组照常执行），工件总会上传。

## 服务差异与疑似客户端缺陷

报告的 `findings` 由实际观察生成，并附原始PROPFIND XML与access log：

- `percent_named_child_refuses_entire_listing`：一个外来 `%` 文件名使整个目录列表失败。
  同步命名空间不会出现这种名字，但用户书籍目录可能出现。
- `display_name_falls_back_to_percent_encoded_component`：服务端不提供 `DAV:displayname` 时
  （mod_dav_fs），`exr_webdav_list` 返回仍为百分号编码的路径分量作为显示名。
- `xml_structure_bound_rejects_shard_below_2000_entry_ceiling`：若某服务的2000项Depth:1应答
  超过客户端20000个XML元素的结构上限，则文档声明的2000项／4 MiB分片上限对该服务不可达。

这些只作为最小复现与拟改共享文件（`extras/webdav/src/webdav.cpp`）交给root协调所有权；
本包不修改该文件，也不为通过而放宽限额或改写断言。

## 云端结果

受测源码 `b870a2f1edc590019c0c76545969627e4de35a7d`，
[run 40054114195](https://github.com/NoGod3524/EXReader/actions/runs/40054114195) attempt 1：

| 服务 | job | 结果 | 工件 |
| --- | --- | --- | --- |
| Nextcloud 33.0.10（SabreDAV） | 120753145349 | 成功，33/33 | 12544812188，15685977字节 |
| Apache httpd 2.4.68 mod_dav_fs | 120753145555 | 失败，32/33 | 12544677295，15587878字节 |

汇总job 120754200175 对两份工件的身份、digest与原始access log重新核对均无问题，
因Apache报告未通过而整体失败。失败项为
`shard_with_2000_entries_is_listed_and_paged_by_cursor`：mod_dav_fs对恰好2000项的
Depth:1应答为2001个response、24014个XML元素，客户端以“WebDAV XML structure limit exceeded”
（`EXR_DAV_LIMIT`）整体拒绝——是明确拒绝而非截断，但文档声明的2000项分片上限对该服务不可达
（约1666项即触顶）。该失败按原样保留，未改断言或限额；最小复现与拟改文件见
[reader-webdav-interop.json](validation/reader-webdav-interop.json) 的 `findings_for_root`，
待root协调 `extras/webdav/src/webdav.cpp` 的所有权。百分号子项整表拒绝在两服务上均复现。

先前的 run 40053615279（`6df34306`）同样是Nextcloud成功、Apache同一项失败，汇总因工件根路径错误未能读取报告；
它作为保留失败记录，不作为证据。

## 证据与限制

### root 共享修复候选（待真实服务复验）

原两轮失败及上述 JSON 均保留。root 已在独立共享候选
`dfc711cc91d6059d6bd8b5062249dafd890fa6d9` 修复 XML 分项预算、一次解码显示名及
无歧义 `%25` 文件名；[run 40054872622](https://github.com/NoGod3524/EXReader/actions/runs/40054872622)
Linux 原77+新增12、Windows 原76+新增12均成功。详见
[兼容性修复](READER-WEBDAV-COMPAT.md)。这不替代真实服务复验。

本候选 workflow 要求此固定客户端提交为祖先，apps/extras 与它逐项相同；互操作改动
仍限于本包路径。2000项、2001项拒绝等原断言保留。两个百分号场景改为要求合法名称
成功列出/下载并核对服务端编码路径，第二重编码仍须在请求前拒绝；显示名断言从
“编码或解码均可”收紧为一次解码后的精确字节。修后真实服务结果尚待同次云端运行。

工件 `reader-webdav-interop-<service>-<run>-<attempt>` 含 `result.json`、原始access/error/容器日志、
Nextcloud日志、原始PROPFIND XML、全部消费者调用、两端及辅助产品库、原件与缓存、公开证书
和构建日志；私钥不进入工件。汇总工件 `reader-webdav-interop-summary-<run>-<attempt>`。
受测SHA、run/attempt/job、工件ID/字节/digest与结论登记在
[reader-webdav-interop.json](validation/reader-webdav-interop.json)。

结论仅针对上表两个固定服务、Linux libcurl后端和声明场景。Docker服务无法在Windows runner上运行，
因此本包不覆盖WinHTTP；也不构成真实用户云盘、移动端、六平台客户端、UI或产品完成的验收，
不继承原TLS夹具的其他平台结论。
