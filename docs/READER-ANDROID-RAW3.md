# Android 原始选择器实际宿主候选

状态：独立候选验收通过，`accepted=true`、`adopted=false`。授予范围为 API34 default x86_64 模拟器上的显式 raw3 实际宿主。

分支 `codex/reader-android-raw3-candidate` 从共同源码 `3c8c9eabbd9e8a5001db10b7a1a92cf69be1c223` 普通合并已封存家族 `0793b26256e1397ba0f60d27de7d090fad61af81`；合并提交 `09377761748cd5549bc864e932e5edd38019142b`。七个模块的受测源码仍是 `56793e7ca4f8ecdc5f2d9c3394fce4e201aca275`，本包不修改模块实现或 SDK。

## 显式开关与实际边界

Gradle `-PexrSelectorBytes=true` 对应 CMake `EXR_READER_SELECTOR_BYTES_CANDIDATE=ON`，默认关闭。ON 必须同时启用 Reading 和 Sync，精确使用 Revisions0.4、ReadingState/ReadingCommands/AnnotationView/Commands/Sync/Session0.2。SDK仍为真实3.41候选，ProductCatalog0.1与WebDAV0.2不变。

现有 Catalog JNI 及 Session JNI 在整个二进制生命周期固定 raw 能力，所有 revision/typed command/view/decode/session入口沿该能力分派。SDK JNI 与 `NativeReadingSdk` 的 byte[]＋显式长度边界保持原字节，固定页 selector 不经 Java 字符串转换。Debug 探针只观察七个真实 raw 符号的版本与 provider、原 MAX2；Release 不包含探针。

## 私有待确认请求

- 旧 private request v1 的 13 个字段和写出顺序保留，读取后 writer 固定2；raw重试不会因为 selector 含NUL自动升级。
- 新 private request v2 增加显式 `anchor_version`。新固定页选3，重排选2；明确恢复使用已验证保留 wire 的源版本，NOTE_TEXT 保持源版本。
- 实际 UI 保存后不确定响应的进程终止，会保留相同 ID、观察父集合及捕获；成功确认才清除。候选中的旧 v1 NUL 失败保留原私有文件字节，等待用户明确处理。
- anchor3 的 NULL exact 表达式可保留，但 JNI 不创建可导航 capture，也不授予可恢复位置。NULL 与非NULL空字节数组保持区分。

## 云端验收设计

原18协议阶段、Java20和默认OFF的原130业务判据不变并实际执行；原默认sender8项保留。新ON的实际宿主测试包括：

- 同一真实8845B PDF，SHA-256 `5627a430fa04cbe11d38eb2682e336ef21e147d445753ed46ed11a7d5e3167cc`，实际公开 SDK 点0..0的NUL suffix，以及以该真实suffix长度为合法end再次capture的非空NUL exact。
- 原四格式4份原件、11条选中记录和完整19条实际已提交wire及父图。出口只导出公开 retained/outbox 原字节。
- 实际 MainActivity UI 的 private v2 保存、已提交响应边界的真实进程终止、新进程按原请求重试并公开 FOUND/重捕获。
- 旧 v1 private request 保持writer2/NUL失败与原字节；实际 MainActivity按源1/2恢复、NOTE_TEXT不升级；NULL位置和错误owner负例。
- 原Android HTTPS后端上的真实 NativeSync/Session worker执行256 shard，传送实际原件和wire、关闭；新接收进程不预置SDK原件，真实下载后再由新SDK owner导入、打开UI并逐字节核对11条记录与公开FOUND/重捕获。
- 实际 Apple raw sender `15dab6b2270dc296ed6239db67ced2e22d255e65` / run `40196978163` attempt1 的原始ZIP `12600789926`，77,056,135B，SHA-256 `92be56ffa04d7c334d4811a42821a314089b4f8ae01746f0dfdf456b5eab9bd5`。仅在Actions认证native/strict成功、原ZIP身份、完整inventory与真实manifest后，原字节经实际Android HTTPS接收并在新进程独立FOUND/重捕获；不以此授予同源码双向。
- 真正 Mac NULL 负例单独来自同一原始ZIP的 `profiles/source-version-and-NULL-operations/reader-catalog.db`。Actions核数据库及可选WAL原字节后只读提取 `body_json`，逐条核保留散列，携带该NULL实体完整父图与同PDF书目祖先；不改写wire或数据库。单独经实际NativeSync HTTPS接收，实际SDK owner导入下载原件后由typed接口及真实UI拒绝导航，再新进程核保留字节与拒绝结果，不计入正常11条FOUND记录。

所有构建、语法检查、夹具、执行和工件解包认证均在 Actions。当前独立 Apple→Android 实际接收已通过；同源码双向、真机、主线默认启用及完整产品仍未授予。

## 已封存的云端证据

受测源码 `4a04a9cc74dde67f755c87e87b278d63a254a3ac`，[run 40207467982 / attempt 1](https://github.com/NoGod3524/EXReader/actions/runs/40207467982) 全部成功：Android `121211376063`、原协议 `121211375764`、严格汇总 `121216568574`。后续提交仅更新本文件及验收JSON。

- 默认OFF原130业务判据和原sender8项全部执行通过；原18协议阶段、Java20、真实SDK3.40/3.41各19项owner检查保留。
- 显式ON共19项、13个不同进程报告及1次真实进程终止边界通过。新private v2的原ID、父集合、原捕获字节在真实终止后重试，保留writer3且不重复提交；旧private v1真实NUL拒绝仍保留原字节。
- 本端实际sender导出4原件、11正常记录、完整19wire，manifest SHA-256 `65a7c6e2be7a0d80e1a7c9eed3731383aa9bdbc71cfd09f89ce63861193b5345`；实际native HTTPS推/收及新SDK owner逐条FOUND/重捕获通过。
- 固定Mac原包为15wire、4原件、11正常记录，manifest SHA-256 `f0960b35374e12827a8966f7022dc3f632e44c87419ca1482288386fb8031566`。实际native HTTPS接收后，新SDK owner的11条独立FOUND/重捕获通过。
- 真Mac NULL单独为3条原wire及1份固定PDF，manifest SHA-256 `86bd72f1609f38b3e006af1eb62172104262e70416a0a8d3a6a83dd968e064b7`。原数据库147456B，SHA-256 `4731ac025a34c435b8b7cc50ba128e0c484c736c2fde6d3ae5658593ed9f3389`，无sidecars；NULL revision `2a490dc51d514032a2815e802c8b3f48`。真实HTTPS接收、SDK owner导入原件、typed无capture/不可恢复、实际UI拒绝导航以及第二新进程重复核验均通过，不计入11条正常FOUND。
- Debug和Release均通过实际archive/provider、唯一SDK DSO及唯一产品SQLite审计；Release无raw测试探针。Debug APK SHA-256 `860927a89eb7ab2e6ffcd93d596e7206a830f15d396be0e0135bf82bedb0b5f3`，实际SDK DSO SHA-256 `a345ab4c1def2e864a76b9e879da8a372e8821ad09b7991c8fe4e04626b2e8ac`。

| 原始工件 | ID | ZIP字节 | SHA-256 |
| --- | ---: | ---: | --- |
| 实际sender原包 | 12604233206 | 18682 | `a38bffdb57ca35699e21b902def18a9d584a6055b7fbef41995e61b240c6168c` |
| 实际宿主及全部raw证据 | 12604412854 | 113970957 | `c3db2ad1a2e31bc53d01620f2ef90e02a976e3b4f90ac76ed2e179c7c9052805` |
| 原协议与SDK owner证据 | 12604077135 | 53286742 | `3a4785c3f9060ecb6053db898fbeebc9c60f52688df9374830db0f1a5bf948ee` |
| 严格汇总 | 12604863663 | 3328 | `03b8c54ea4b8e15a379d10bd508b09cc80b25cecf2fb90fff5e73e7773bf98f7` |

工件有效期均为 `2027-01-23T15:33:00Z`。同轮原默认工件及所有job身份完整登记在 `docs/validation/reader-android-raw3.json`。五次早期失败原run均保留：分别为新增夹具误用anchor1点、按SDK临时书名筛选已保留产品标题、第二重开误点书架Refresh、ADB缺失marker文本误当JSON、共享前置只识别书架SDK标签；均修复于新测试，不改生产行为或既有验收判据。
