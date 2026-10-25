# 固定页原始选择器独立候选

状态：未验收、未采用。固定起点 b93b4a2f9ac24d7d0fc4d48c917dae11bec4baf7。
仅四个应用模块提供显式 raw-v3 候选，SDK、schema1、宿主和默认依赖链保持。

默认 CMake 选项 `EXR_READER_SELECTOR_BYTES_CANDIDATE=OFF`，原 Revisions0.3、ReadingState0.1、ReadingCommands0.1、AnnotationView0.1 依赖保持 EXACT。
显式 ON 在独立安装前缀构建0.4/0.2/0.2/0.2版本族，内部精确依赖候选版本，不与旧前缀混合链接。

新入口为 `reader_revisions_open_raw_v3` 及显式 `_raw_v3` revision操作、`reader_rs_encode_fixed_v3`、`reader_rs_decode_raw_v3`、`reader_rs_resolve_fixed_v3`、`reader_rc_apply_fixed_v3`、`reader_av_open_raw_v3`/`reader_av_page_get_raw_v3`。能力在store创建时固定。旧入口拒绝raw store，旧MAX宏仍为2，默认writer仍为v2且保留GAP_NUL。

外层 revision version1 与schema1不变。只有fixed_page anchor3的exact/prefix/suffix使用严格对象 `{base64,size}`；JSON null/零长度与空字符串/零长度分开，数据按size读取，NUL不截断。page ID和其它标识继续严格UTF-8且拒绝NUL。exact上限65536B，prefix/suffix各128B/32 scalars，规范Base64含padding及零pad bits。只有raw exact的精确JSON路径在显式v3下允许87384字符，普通文本上限不变。

NULL exact可被无损传输和解码，但不是合法SDK fixed capture：typed内容不可用，resolve不授予FOUND。真正捕获仍由公开SDK生成；新reader读旧wire不重编码。NOTE_TEXT保留实际来源版本、全部长度和NULL标签，delete/restore/retry复用原事务及完整父图规则。

专属Actions核对同一真实`pdf-public-text.pdf`（8845B、SHA256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`）的page-1、0..0真实NUL点及真实非空NUL范围，另进程接收、缺父补齐、typed SAFE、FOUND、复捕获及第三进程重开。原v1/v2与默认构建逐字输出对照另行执行。

本候选尚无云端结果；不授予实际Android/Apple互通、真机、性能或主线采用。原sender138、原130证据仍属各自受测源码。
