# EPUB DRM：只读资源解码

支持公开的 **Readium LCP Basic Profile 1.0**：SHA-256(UTF-8 口令) 得到用户密钥；解密 `key_check` 并与许可证 `id` 比较，再解密 32 字节内容密钥；按 `encryption.xml` 解密各资源。不是 PBKDF2。标准路径 `META-INF/license.lcpl` 和兼容路径 `META-INF/license.lcp.json` 均可用，两者同时出现视为歧义错误。

这是 **Basic Profile 的资源解码器**，不是通过认证的商用 LCP 客户端。当前不校验许可证 RSA 签名、证书链或 CRL；许可证来源及信任校验须由宿主负责。生产 profile 1.0、2.x 返回 `EXR_DRM_UNSUPPORTED`，接入需要 EDRLab 提供的生产密码学模块、根证书及认证流程。

## 宿主 API

```c
exr_publication *publication = NULL;
exr_error error = {0};
exr_status status = exr_publication_open_ex(path, utf8_passphrase, &publication, &error);
/* 成功后使用原有 publication_load / session / chapter_reader 管线。 */
exr_publication_free(publication);
```

同时提供 `exr_publication_open_memory_ex(format, data, size, passphrase, out, error)` 和 `exr_publication_open_source_ex(source, passphrase, out, error)`。原三个 API 的 ABI 不变，等同于传入 `NULL` 口令。`NULL` 表示未提供，空字符串表示提供了空口令；普通书忽略此参数。口令只在 open 调用中借用，不保存。源的 release 回调只在 open 成功后转移，最后一个出版物、文档或会话引用释放时调用一次。

| 场景 | 错误码（追加到原枚举末尾） | 示例原因 |
| --- | --- | --- |
| 无口令 | `EXR_DRM_PASSPHRASE_REQUIRED` = 14 | LCP passphrase required，附许可证 hint |
| 口令错 | `EXR_DRM_PASSPHRASE_INCORRECT` = 15 | Incorrect LCP passphrase (license key_check mismatch) |
| 已过期 | `EXR_DRM_LICENSE_EXPIRED` = 16 | LCP license expired at 2001-02-03T04:05:06Z |
| 算法/profile/DRM 不支持 | `EXR_DRM_UNSUPPORTED` = 17 | Unsupported LCP profile or algorithm |
| 损坏/不完整/尚未生效 | `EXR_DRM_LICENSE_INVALID` = 18 | 缺失许可证、无效时间、损坏密文或原长不一致 |

失败时 publication 输出为 NULL，`error` 可省略。结构上有效的 `key_check` 解密不匹配归为口令错误；损坏的 key_check 也可能产生相同结果。时间采用系统 UTC，支持 RFC3339 时区偏移与小数秒；检查 `rights.start/end`，到达 end 时拒绝打开。

## 内存与资源读取

- 原 ZIP 保持加密；不重打包明文 EPUB，不创建明文临时目录。读取一项资源时才进行 AES-256-CBC 解密，再交回已有 EPUB 管线。内容密钥在最后一个共享归档引用关闭时清零。
- CBC 前 16 字节为 IV；按 XML Encryption 规则使用最后一字节移除 1–16 字节填充，不要求每个填充字节都相等。压缩方式 0 原样返回，8 使用 raw DEFLATE，并核对 `OriginalLength` 和完整输入消费。
- 普通资源、章节加载、带预算的资源和章节流接口共用解码器。单项资源至多 32 MiB；带预算接口也计入密文、明文和 inflate 工作区。加密章节完整解密后按至多 32 KiB 分块投递，尚未实现密文随机区间解码。
- 许可证至多 64 KiB，encryption.xml 至多 4 MiB，JSON/XML 嵌套至多 32 层；拒绝重复已知 JSON 字段、DTD、无效 UTF-8、缺失/危险资源路径、重复资源及超额解压。仅有字体混淆的 EPUB 保持原资源行为。

选择内存方案是为了复用源回调与资源生命周期，省去临时文件权限和异常退出清理。代价是一次解密需容纳一项资源；现有资源上限和宿主预算约束内存。宿主取得的正文及资源缓冲区由宿主管理。结构化 EPUB 导出仍拒绝带 encryption.xml 的书。

## 未做的部分

- **借阅到期回收未实现**：打开时检查日期；不联系 License Status Document 服务，不做登记、续借、归还、撤销或阅读中途回收。库层没有网络与设备会话管理，需宿主接入这些流程。
- **Adobe ADEPT 未支持**：当前没有获授权的完整测试组合（加密 EPUB、rights.xml/许可证、可用用户私钥或已解封内容密钥、无 DRM 对照）。遇到 rights.xml 或不支持的资源算法返回明确错误。获得这些材料后才能验证只读解密；设备激活不在本任务范围，需要 Adobe 授权的客户端集成。
- 无独立 `.lcpl` 下载/注入流程，宿主需提供包含许可证的 EPUB。无签名/PKI 验证和商用 profile 支持，边界见上文。

ADEPT 样本获取途径：[官方 Sample eBook Library](https://www.adobe.com/uk/solutions/ebook/digital-editions/sample-ebook-library.html)。本次尝试该页的 `aliceDynamic.epub` 和 `GeographyofBliss_oneChapter.epub` 下载均返回 HTTP 403，也未提供可用用户密钥。授权客户端/SDK 的后续获取参见 [Adobe 平台迁移说明](https://www.adobe.com/support/digitaleditions/)；激活不在本库内实现。

## 测试与复现

离线 CTest 新增六组：`native-lcp-normal`、`credentials`、`expired`、`unsupported`、`malformed`、`lifetime`。读取仓库内 23 个合成 EPUB；包括源短读、出版物先关而文档仍可读、输入内存可释放、逐项资源比较、预算分配失败遍历和取消。没有修改既有测试断言。

```sh
cmake -S . -B build -DEXR_ENABLE_LCP=ON
cmake --build build --parallel 4
ctest --test-dir build --output-on-failure
python tests/lcp_acceptance.py --samples build/lcp-samples --library build/libexreader.dll --probe build/exreader-lcp-test.exe --output evidence/drm-lcp-20261109/acceptance.json
```

Linux/macOS 调整共享库和可执行文件后缀。脚本首次下载下列公开样本并校验固定 SHA-256；原书、加密书均只读。原生 probe 对比所有 manifest 资源的解密后字节和章节文本，完成分页。

- [EDRLab r2-shared-js 样本及口令说明](https://github.com/edrlab/r2-shared-js)：`misc/epubs/wasteland-otf-obf_LCP_dan.lcpl.epub`，口令 `dan`，SHA-256 `490bdc43b358dae88227865bb8ae9b2c4188c59d7d418a86219ef082aba6e093`。
- 同目录 `wasteland-otf-obf.epub` 是未加 LCP 的原书（保留相同字体混淆），SHA-256 `6805fe8c45134a141dbc0dc5b0357774112adb977095b19427baa4c260372cbd`。
- 合成样本使用独立的 Python cryptography 生成。只在重生成时需要该包；下载 [Readium 公开测试证书及密钥](https://github.com/readium/readium-lcp-server/tree/master/test/cert) 后运行：

```sh
python tools/generate_lcp_fixtures.py --certificate <cert-edrlab-test.pem> --key <privkey-edrlab-test.pem>
```

固定 IV 只用于可复现测试；合成许可证由公开测试私钥签名，密钥不打包到 SDK。生成器不是生产许可证发行工具。

默认启用 `EXR_ENABLE_LCP`，复用已有 Mbed TLS 3.6.7 AES/SHA-256，增加其 Base64 模块。与 PDF 组件开关独立；关闭 LCP 时入口保留，带许可证的 EPUB 返回 `EXR_DRM_UNSUPPORTED`。

依据：[Readium LCP 1.0 第 2、4、6 节](https://readium.org/lcp-specs/releases/lcp/latest.html)、[profile 注册表](https://readium.org/lcp-specs/registries/profiles)、[EDRLab 生产 profile 说明](https://www.edrlab.org/readium-lcp/encryption-profiles/)。
