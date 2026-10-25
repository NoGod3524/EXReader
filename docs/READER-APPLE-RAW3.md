# Apple 原始固定页选择器独立宿主候选

状态：源码与云端验收入口准备；尚未运行本包 native，`accepted=false`。

起点 `896420028fa3923f3713afb673f56b913f93373f`，独立分支 `codex/reader-apple-raw3`。普通合入 core `0737d03c1316295a210aa527833c05054d29c1d4` 与已通过的七包伴随家族源码 `56793e7ca4f8ecdc5f2d9c3394fce4e201aca275`（run40192929457 / attempt1），并保留其证据 HEAD `0793b26256e1397ba0f60d27de7d090fad61af81`。SDK保护树精确 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，产品schema1、wire envelope1和旧anchor1/2不变。带入的三个Android构建入口恢复起点字节，Android宿主生产不在本包内改动。

## 构建与实际调用

默认 `EXR_APPLE_RAW3=OFF`，原调用参数、库链接顺序与provider限制保留。显式 `--selector-bytes-candidate --product-prefix <独立目录>` 才构建raw家族；SDK前缀禁止兼作候选产品前缀。Revisions0.4.0与State/ReadingCommands/AnnotationView/Commands/Sync/Session0.2.0全部EXACT查询实际安装Config，单独记录proof；WebDAV0.2与Catalog0.1保持。

Swift同时传入 `-Xcc -DEXR_READER_SELECTOR_BYTES_CANDIDATE=1` 与独立条件 `EXR_APPLE_RAW3`，候选产品头优先，七个实际raw实现符号及归档对象来源逐项核对。第二SQLite、静态SDK和`libreader_reading_state.a`的旧禁令保留，实际解析继续使用唯一动态SDK。

HostCatalog实际打开raw revisions，并沿全部typed book操作使用raw API。HostReadingWorker的heads/get/selected/decode/view/apply全部显式raw；HostAccountSession实际create raw，由原单worker执行raw sync/command链。默认分支仍调用原API。

## 私有请求与保留记录

旧私有request version1始终writer2；读与重试不会根据新构建或mode升级它。新候选请求version2持久保存明确`anchor_version`1/2/3：新固定页选择3，原重排/EPUB选择2；恢复和正文编辑显式传保留源的实际版本。请求原始文件、revision ID、bootstrap与parents在重试时不重写。旧NUL请求继续失败；新raw3使用新ID与独立profile。

固定页capture与decoded selector保持`Data?`和显式size，NULL与非NULL空值分开。quote按exact_size读取并保留Data；`hasLocation`同时要求typed content_available、位置与非NULL exact。NULL表达可以保留，不能导航，也不补成空字符串。

## 首轮真实 native 计划

全部构建、语法检查、夹具、证书信任、工件处理只在Actions。

- 原Apple owner19检查分别运行在真实SDK3.40/3.41；原兼容18进程、Java策略20保留。原实际Apple sender对同一NUL PDF的失败继续执行，不改成容易文件。
- 实际HostSession/Worker发送四格式11条记录（TXT3、EPUB3、PDF3、CBZ2点），逐项公开SDK FOUND、复捕获与SDK状态不变；同一8845B PDF / SHA256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc` 的0..0点suffix和完整非空range exact必须实际含NUL。
- 新独立owner接收完整原wire/父图，真实重开；旧failed pending在raw构建中仍writer2失败，原文件与ID/parents不变；在durable-save/实际commit边界记录标记并对实际进程发SIGKILL，原请求重试before created=1、after created=0。原兼容控制的73/74退出也继续执行。
- 实际源v1/v2的NOTE_TEXT/delete/restore保持源版本；显式NULL负例不授typed location或FOUND。
- 实际HostAccountSession通过原Foundation HTTPS transport完成256shard push/GET认证/ack、鲜接收与重开；网络接收阶段禁止手动receive补入缺失wire，SDK导入只使用实际下载的缓存原件。证书使用Actions临时测试信任，认证值和私钥不上传。

首授仅实际macOS Apple sender、独立owner与原生HTTPS Session范围。Android双向、iOS UI、真机、性能及共同MAX2主线采用继续独立验收。
