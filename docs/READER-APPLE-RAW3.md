# Apple 原始固定页选择器独立宿主候选

状态：独立 macOS 实际宿主候选已通过；默认关闭，尚未采用到共同 MAX2 主线。

起点 `896420028fa3923f3713afb673f56b913f93373f`，独立分支 `codex/reader-apple-raw3`。普通合入 core `0737d03c1316295a210aa527833c05054d29c1d4` 与已通过的七包伴随家族源码 `56793e7ca4f8ecdc5f2d9c3394fce4e201aca275`（run40192929457 / attempt1），并保留其证据 HEAD `0793b26256e1397ba0f60d27de7d090fad61af81`。SDK保护树精确 `edddc463c06ed5731195cdb8f06b2df6dff7699e`，产品schema1、wire envelope1和旧anchor1/2不变。带入的三个Android构建入口恢复起点字节，Android宿主生产不在本包内改动。

## 构建与实际调用

默认 `EXR_APPLE_RAW3=OFF`，原调用参数、库链接顺序与provider限制保留。显式 `--selector-bytes-candidate --product-prefix <独立目录>` 才构建raw家族；SDK前缀禁止兼作候选产品前缀。Revisions0.4.0与State/ReadingCommands/AnnotationView/Commands/Sync/Session0.2.0全部EXACT查询实际安装Config，单独记录proof；WebDAV0.2与Catalog0.1保持。

Swift同时传入 `-Xcc -DEXR_READER_SELECTOR_BYTES_CANDIDATE=1` 与独立条件 `EXR_APPLE_RAW3`，候选产品头优先，七个实际raw实现符号及归档对象来源逐项核对。第二SQLite、静态SDK和`libreader_reading_state.a`的旧禁令保留，实际解析继续使用唯一动态SDK。

HostCatalog实际打开raw revisions，并沿全部typed book操作使用raw API。HostReadingWorker的heads/get/selected/decode/view/apply全部显式raw；HostAccountSession实际create raw，由原单worker执行raw sync/command链。默认分支仍调用原API。

## 私有请求与保留记录

旧私有request version1始终writer2；读与重试不会根据新构建或mode升级它。新候选请求version2持久保存明确`anchor_version`1/2/3：新固定页选择3，原重排/EPUB选择2；恢复和正文编辑显式传保留源的实际版本。请求原始文件、revision ID、bootstrap与parents在重试时不重写。旧NUL请求继续失败；新raw3使用新ID与独立profile。

固定页capture与decoded selector保持`Data?`和显式size，NULL与非NULL空值分开。quote按exact_size读取并保留Data；`hasLocation`同时要求typed content_available、位置与非NULL exact。NULL表达可以保留，不能导航，也不补成空字符串。

## 真实 native 范围

全部构建、语法检查、夹具、证书信任、工件处理只在Actions。

- 原Apple owner19检查分别运行在真实SDK3.40/3.41；原兼容18进程、Java策略20保留。原实际Apple sender对同一NUL PDF的失败继续执行，不改成容易文件。
- 实际HostSession/Worker发送四格式11条记录（TXT3、EPUB3、PDF3、CBZ2点），逐项公开SDK FOUND、复捕获与SDK状态不变；同一8845B PDF / SHA256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc` 的0..0点suffix和非空range exact实际含NUL。range终点取实际SDK点suffix的字节数，再调用真实SDK capture；不使用固定页UI快照的0..<0占位pageRange。
- 新独立owner接收完整原wire/父图，真实重开；旧failed pending在raw构建中仍writer2失败，原文件与ID/parents不变；在durable-save/实际commit边界记录标记并对实际进程发SIGKILL，原请求重试before created=1、after created=0。原兼容控制的73/74退出也继续执行。
- 实际源v1/v2的NOTE_TEXT/delete/restore保持源版本；显式NULL负例不授typed location或FOUND。
- 实际HostAccountSession通过原Foundation HTTPS transport完成256shard push/GET认证/ack、鲜接收与重开；网络接收阶段禁止手动receive补入缺失wire，SDK导入只使用实际下载的缓存原件。证书使用Actions临时测试信任，认证值和私钥不上传。

首授仅实际macOS Apple sender、独立owner与原生HTTPS Session范围。Android双向、iOS UI、真机、性能及共同MAX2主线采用继续独立验收。

## 云端封存

受测源码 `15dab6b2270dc296ed6239db67ced2e22d255e65`，run [40196978163](https://github.com/NoGod3524/EXReader/actions/runs/40196978163) attempt1。实际macOS producer `121179826434` 与严格汇总 `121186031984` 均 success；macOS15.7.9 / ARM64。原兼容18进程、每个真实SDK的owner19检查与Java策略20同轮通过。

12个独立实际进程阶段全部通过：旧NUL待完成请求保持writer2并拒绝；实际sender11条、独立owner接收与新进程重开；源v1/v2编辑、删除与恢复；NULL负例；durable-save与实际commit两处SIGKILL退出均为-9，重试分别created1/0；实际HostAccountSession的HTTPS发送、接收与重开各完成256shard一轮。raw程序SHA256为 `5f59e17cf48e77b1ef8766695bf109895feac5e628bc18d9804ee625a2749913`。

原工件 `12600789926`，`apple-raw3-native-40196978163-1`，77,056,135B，ZIP SHA256 `92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5`，有效期至2027-01-23T13:18:06Z。严格汇总在Actions下载原ZIP，核对字节、散列、有效期、源身份与每个文件清单后授予macOS范围。汇总工件 `12601910101`，509B，SHA256 `ff5bf72b40c5481b82fa5ed2e4992d5db62b424e804b1b419f9a0eee87196f9c`。

供独立接收者使用的原包为ZIP内 `sender-bundle/manifest.json`、`originals/`、`revisions/`和`proofs/`；manifest schema1登记4原件、11条reading记录、完整父图与原wire、实际程序和唯一SDK DSO身份。`result.json.files`登记manifest与全部文件的字节和散列。NULL selector与非NULL空字节串分开传输。

首轮失败 run [40195832816](https://github.com/NoGod3524/EXReader/actions/runs/40195832816) / source `336b083da6b9000735febdb6a72941a6202f9d81` 保留。失败在新probe把固定页快照0..<0占位范围当成highlight选区；真实ReadingCommands拒绝空highlight。修复仅改变probe范围的取得方式，生产实现、原PDF、原消费者与断言未改。封存提交只改本说明和验收JSON。
