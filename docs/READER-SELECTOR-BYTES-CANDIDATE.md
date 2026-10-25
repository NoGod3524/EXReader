# 固定页原始选择器独立候选

状态：独立候选核心与typed模块已通过Linux/Windows同源云端验收，尚未采用。固定起点 b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7。
仅四个应用模块提供显式 raw-v3 候选，SDK、schema1、宿主和默认依赖链保持。

默认 CMake 选项 `EXR_READER_SELECTOR_BYTES_CANDIDATE=OFF`，原 Revisions0.3、ReadingState0.1、ReadingCommands0.1、AnnotationView0.1 依赖保持 EXACT。
显式 ON 在独立安装前缀构建0.4/0.2/0.2/0.2版本族，内部精确依赖候选版本，不与旧前缀混合链接。

新入口为 `reader_revisions_open_raw_v3` 及显式 `_raw_v3` revision操作、`reader_rs_encode_fixed_v3`、`reader_rs_decode_raw_v3`、`reader_rs_resolve_fixed_v3`、`reader_rc_apply_fixed_v3`、`reader_av_open_raw_v3`/`reader_av_page_get_raw_v3`。能力在store创建时固定。旧入口拒绝raw store，旧MAX宏仍为2，默认writer仍为v2且保留GAP_NUL。

基础store入口声明在独立的`reader_revisions.h`；选中、分页和受控事务入口仍在`reader_projection.h`。C与C++安装消费者分别编译，基础C消费者仅包含基础头。关闭选项时新符号不进入库，四个包与版本宏保持旧值；开启时C版本宏与0.4/0.2安装版本一致。OFF安装清单与原b93构建相同，但五份公共头含新增条件声明/版本分支，文件字节不同；不声称整个安装包逐字不变。原v1/v2生成wire单独逐字比较。

外层 revision version1 与schema1不变。只有fixed_page anchor3的exact/prefix/suffix使用严格对象 `{base64,size}`；JSON null/零长度与空字符串/零长度分开，数据按size读取，NUL不截断。page ID和其它标识继续严格UTF-8且拒绝NUL。exact上限65536B，prefix/suffix各128B/32 scalars，规范Base64含padding及零pad bits。只有raw exact的精确JSON路径在显式v3下允许87384字符，普通文本上限不变。

解码后的选择器仍遵守公开SDK的UTF-8语义：U+0000保留为一个标量，非法UTF-8拒绝，不修补或替换字节。`{base64:null,size:0}`解码为NULL；`{base64:"",size:0}`解码为非NULL空缓冲；显式size不包含分配的末尾防护NUL。NULL加非零size拒绝。start/end保持原字节偏移，差值必须等于exact_size。

NULL exact可被无损传输和解码，但不是合法SDK fixed capture：typed内容不可用，resolve不授予FOUND。真正捕获仍由公开SDK生成；新reader读旧wire不重编码。NOTE_TEXT保留实际来源版本、全部长度和NULL标签，delete/restore/retry复用原事务及完整父图规则。

`reader_rc_apply_fixed_v3`明确选择新固定页anchor3。`reader_rc_apply_raw_v3`要求调用者显式传1/2/3，恢复旧源可选择原版本；没有自动选择版本。NOTE_TEXT即使传入另一个受支持版本，也保留实际源版本；未知版本拒绝。delete的payload为null，本身没有location/anchor_version。新的put/restore拒绝NULL exact，接收到的NULL表达可原样编辑正文，但不变成可用SDK捕获。

原件身份、完整唯一安全父图和公开SDK FOUND仍是不同边界。纯codec不验证整本SDK原件，纯fixed resolver按唯一page_id与page hint核对页路由；宿主接入仍必须先验证原件format/SHA/bytes和现有parser白名单。本候选不放宽这些宿主策略，也不自动导航或写入SDK笔记/进度。

专属Actions核对同一真实`pdf-public-text.pdf`（8845B、SHA256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`）的page-1、0..0真实NUL点及真实非空NUL范围，另进程接收、缺父补齐、typed SAFE、FOUND、复捕获及第三进程重开。原v1/v2与默认构建逐字输出对照另行执行。

## 云端证据

受测源码 **`eb0a4ac713be25c1487843c19c2d02d579258644`**，SDK源码保持`edddc463c06ed5731195cdb8f06b2df6dff7699e`，实际安装SDK为3.41.0。[Run 40186400653](https://github.com/NoGod3524/EXReader/actions/runs/40186400653) / attempt1：Linux `121147996604`、Windows `121147996787`、strict `121148786664`全部success。

| 每平台检查 | Linux | Windows |
| --- | ---: | ---: |
| 新raw协议与限额 | 30 | 30 |
| 新真实capture派生图负例 | 11 | 11 |
| 原revision完整协议 | 59 | 59 |
| 原v2协议完整正反例 | 28 | 28 |
| 原v1实际SDK探针 | 121 | 121 |
| 原v2实际SDK探针 | 116（18案例） | 116（18案例） |
| 原reading-commands完整探针 | 1413 | 1413 |
| 原annotation-view完整探针 | 56 | 56 |

新实际PDF流程还执行了独立发送进程、缺父/补齐接收进程、第三进程重开、实际命令逐份wireCapture对照、公开SDK FOUND与重新捕获逐字节/NULL标签核对、NOTE_TEXT/delete/restore/retry、事务写锁失败、resolve/view取消、NULL exact表达不授予FOUND，以及显式1/2恢复与未知writer版本拒绝。原v2对同一真实NUL点继续GAP_NUL。baseline b93、OFF、ON三族的原v1/v2输出wire逐字一致；OFF新符号缺席、安装清单相同，五份公共头的条件声明文本差异单独保留。

| 原工件ZIP | ID | 字节 | SHA-256 |
| --- | ---: | ---: | --- |
| Linux | 12595319907 | 51299701 | `67aa151c5a1ef67d5c7f4ec5d02e7de16c8086f3bb86c967d01ba0d878a2f4ee` |
| Windows | 12595969192 | 55351821 | `25ac6f7d7ce4a2754946fd82593b3cfc2c187fbdbb7a6afbe4a2c7639a6fdfed` |
| strict summary | 12595954258 | 738 | `d38e56a23443504c7ce3d9778b692921d5a3d089fba0e375b28478438adbc968` |

三份工件有效期均为`2027-01-23T10:50:16Z`。strict认证同run/attempt成功producer、source、API字节/digest/有效期、原ZIP内实际执行程序与全部日志散列；独立读取公开SDK直接导出的selector二进制，与wire Base64/size逐项对照。两平台选中wire完整相同，真实NUL均保留。

前两轮失败分别为新探针公开SDK函数参数数目错误、expected SHA与输出info别名；随后三轮两平台producer均通过，但strict因urllib把API认证头带入签名Azure重定向而401。修正为复用原已验`gh api`下载后，`ce929e60` / run40186197539整轮通过；最后对公开头归属的调整在eb0a4ac7另行整轮重跑通过。所有失败记录留在验收JSON与Git历史。

授予范围仅为安装后的codec/revisions/reading-commands/typed-view候选核心。`accepted=true`、`adopted=false`；实际Android/Apple宿主接入、双向互通、macOS、SDK3.40候选执行、真机、性能与主线采用均未授予。原sender138、原130仍属各自受测源码。
