# C4 产物校验、签名与可复现性实测

任务起点：`ed252fb6`，Windows x64；当前源码改动由 manifest 的 override 哈希和完整源码指纹标识。
编译器 GNU/MinGW **16.2.0**，**cmake version 4.4.2**，Ninja，Release。
manifest SHA256：`795c22af87d4a0f4f73251030ec478352fd4e2476bcf1dfd21c974e9f0829f7c`。

## 验收结果

- 两轮均执行 `cmake --build ... --clean-first --parallel 4`，清理后重新编译/链接；分别安装到新目录。
- 每轮 **3** 个发布文件校验通过；**355** 个安装文件的全部 SHA256 一致。
- 两轮共用同一份 manifest、源码、依赖、工具链、机器及构建路径；外部产物与包内均带 `SHA256SUMS`。
- 新增发布边界测试 **22/22**；原发布协议 **54/54**；发布计划 **58/58**。
- CTest：修改前 **234/234**，修改后 **235/235**，无原测试丢失、无失败/跳过；最终工具兼容修正后单独复跑发布 CTest 通过。
- 真书回归 **19/19 本，11,318 页**，页数变化 **0**，逐页像素哈希变化 **0**。
- 编译层检查：118 objects，1340 symbol references；新增反向依赖 **0**、反向 include **0**。
- `.github/`、`src/`、`include/` 未改；workflow 只提供 [片段](../../tools/release/workflow-snippet.yml)。既有测试断言未改。

## 两组 SHA256

| 文件 | 第一次清理后构建 | 第二次清理后构建 |
| --- | --- | --- |
| `EXReader-SDK.tar.gz` | `07c0e315df9b4c47f532842af4b76b9fd0edfbc9102db6f2e54bbda665c65c19` | `07c0e315df9b4c47f532842af4b76b9fd0edfbc9102db6f2e54bbda665c65c19` |
| `bin/libexreader.dll` | `b7ab2bc2668e806bf03c957d767d8247dcc708c6d2ea59b74464a6cfc7aea632` | `b7ab2bc2668e806bf03c957d767d8247dcc708c6d2ea59b74464a6cfc7aea632` |
| `build_manifest.json` | `795c22af87d4a0f4f73251030ec478352fd4e2476bcf1dfd21c974e9f0829f7c` | `795c22af87d4a0f4f73251030ec478352fd4e2476bcf1dfd21c974e9f0829f7c` |

原始列表：[run-1-SHA256SUMS](run-1-SHA256SUMS)、[run-2-SHA256SUMS](run-2-SHA256SUMS)。
完整安装文件对照与命令：[reproducibility.json](reproducibility.json)。
两次编译/安装日志：`run-1-build.txt`、`run-1-install.txt`、`run-2-build.txt`、`run-2-install.txt`。
本机可下载的实际包和 DLL 保留在 `build/c4-archive-proof/run-1/artifacts/` 与 `run-2/artifacts/`。

根因修复：DLL 使用 `--no-insert-timestamp`；GNU 静态归档使用 `ar qcD/qD` 与 `ranlib -D`；DLL 导入库通过 `objcopy --enable-deterministic-archives` 归一化元数据。本机 WinLibs 的 `ar` 默认模式为 U（真实时间戳），不能依赖工具链默认值。早期对照的 18 个归档仅成员头元数据不同；本报告保留的是修复后的完整两轮构建。参考 [GNU ar D 模式](https://sourceware.org/binutils/docs/binutils/ar-cmdline.html)。

## 构建输入

[build_manifest.json](../../tools/release/build_manifest.json) 包含编译器/CMake 版本和二进制哈希、Ninja/链接器/归档器哈希、完整 CMake cache、实际 configure 参数、宿主/Python、相关环境变量、源码 revision/tree/改动哈希、生成头文件指纹、依赖来源与实际源码指纹、打包时间/格式/顺序。
源码内容指纹：`7b5e26b7d6e61376a4cbd8d10e56077b99dcf8ce615e05b5db1e8a4ffcfa6711`（5950 个文件）。

| 依赖 | tag/commit | 上游归档 SHA256 | 本机实际源码树 SHA256 |
| --- | --- | --- | --- |
| expat | R_2_9_0 | `6e8ce7b52ebbaa423c59becc7cf1e6875c42e49228c062ac8123c10e700cec27` | `3976c0019c734859d939a344c96ace4484781a2b75d38da41607c60b747a9a48` |
| freetype | VER-2-15-0 | `87c7f1f8699b91e89f773f7dcfa505b044e1dae67f62a55d4e29c3afdcac4fb8` | `a18da793ed72d67b10de33a78ac810ef6845c6fb7c87bb5a6600a2aea520f3c6` |
| miniz | 3.1.2 | `98468f8924934b723276680f85238b6c78bf1f8b49b4459cc9b7214a20e2e9fb` | `d8c7798a831dbd182ef44e62d5e1fe163c3606a609d39b34d33dffc6351227ff` |

另记录 SQLite、stb、OpenJPEG。本次采用与真书回归一致的功能配置：aggregate DLL、PDF/JPX、音频/书架/文本索引开启；ICC、PDF crypto、WebP/TIFF/AVIF、MP3/AAC 关闭，具体选项全部保存在 cache。
本次证明限于同机同路径的未签名产物；MSVC 与跨机器、跨路径构建未作为实测结果。

## 签名

Git GPG 2.4.9：使用独立临时 keyring 的 **TEST ONLY** Ed25519 密钥完成真实 detached signing、验签，并确认篡改 `SHA256SUMS` 后验签退出 1。测试公钥不代表发布者身份。
日志：[gpg-sign.txt](gpg-sign.txt)、[gpg-verify.txt](gpg-verify.txt)、[gpg-tamper-rejected.txt](gpg-tamper-rejected.txt)。
GPG/minisign dry-run 与显式 SHA256-only 回退均运行成功。

Authenticode：CurrentUser/LocalMachine My 证书存储未发现带私钥的代码签名证书；需要 **EV/OV 证书**。
真实 DLL 的 [dry-run](authenticode-dry-run.txt) 给出以下模板及验证命令：

```text
signtool sign /sha1 EV_OR_OV_CERTIFICATE_THUMBPRINT /fd SHA256 /tr RFC3161_TIMESTAMP_URL /td SHA256 stage/bin/exreader.dll
signtool verify /pa /all /v stage/bin/exreader.dll
```

生产顺序为未签名构建复现 → Authenticode（有证书时）→ 打包 → SHA256SUMS → GPG/minisign → 发布。
公钥指纹必须从可信项目渠道取得；纯 SHA256 不提供私钥身份认证。完整使用步骤见 [release README](../../tools/release/README.md)。

## 回归证据与边界

`realbooks-before.json.gz` 与 `realbooks-after.json.gz` 保存全部逐页哈希；[realbooks.diff.json](realbooks.diff.json) 是零差异对照。
本任务起点 `ed252fb6` 的未修改 DLL 已与 11 月 7 日历史基线存在排版差异（旧基线 11,128 页）；因此 C4 的对照是本机新构建的任务起点 DLL，而不是改写历史基线。
`ctest-summary.json` 核对测试集合；两个完整 JUnit/XML 和日志随本报告保存。

修改发布验证器与测试 fixture 的 SQLite 连接释放，修复 Windows/Python 3.14 下临时库文件被锁住的问题；没有改断言。
开发中修正 MSYS GPG 路径、LF JSON 输出及 Python 兼容性时，早期构建被输入冻结检查拒绝；这些部分结果未计入上述两轮实测。
只使用本地构建/测试；未手动 workflow_dispatch、未取消 workflow。创建 draft PR 后的自动 CI 单独记录在 SIGN-OUT.txt。

测试验签材料：[TEST-ONLY-public-key.asc](TEST-ONLY-public-key.asc)、[run-1-SHA256SUMS.asc](run-1-SHA256SUMS.asc) 与 [run-1-SHA256SUMS](run-1-SHA256SUMS)。测试密钥指纹 `9F4FA4A91FFB167C8E3EEECE19FC78ABA24F4924`；它不是正式发布密钥。

真书测试 DLL 与最终复现 DLL 的 SHA256 完全相同：`b7ab2bc2668e806bf03c957d767d8247dcc708c6d2ea59b74464a6cfc7aea632`；内容指纹 `8e51f8a0ad679f1fab702a96aed50dd02ad32d4d3624f0e30b1234ff20cd5434`。
