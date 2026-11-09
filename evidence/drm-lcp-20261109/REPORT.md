# A2 LCP 验收（2026-11-09）

实现公开 LCP Basic Profile 的只读资源解码：SHA-256 用户密钥、AES-256-CBC、IV/填充、raw DEFLATE 与原长核对。`open_ex` / `open_memory_ex` / `open_source_ex` 接受宿主口令；旧 API ABI 保持不变。原 EPUB 保留加密，按资源在内存解码，无明文临时目录。

| 验收项 | 最终结果 |
| --- | --- |
| 公开样本 | EDRLab / Readium r2-shared-js《The Waste Land》，Basic Profile，公开口令 `dan` |
| 成功分页 | **48 页**（仓库 primary.ttf、默认 layout config） |
| 原书对照 | **10 个 manifest 资源、1,612,682 字节全部一致**；章节文本一致 |
| 缺口令 | `EXR_DRM_PASSPHRASE_REQUIRED` = **14** |
| 错口令 | `EXR_DRM_PASSPHRASE_INCORRECT` = **15**；输出 NULL，无崩溃 |
| 过期 | `EXR_DRM_LICENSE_EXPIRED` = **16**；消息包含 `2001-02-03T04:05:06Z` |
| 不支持 | `EXR_DRM_UNSUPPORTED` = **17**；生产 profile / 算法 / ADEPT 检测 |
| 无 DRM 真书 | **19/19，11,116 页、7,580,223 glyphs；页数和每页 SHA-256 全部不变** |
| 全量 ctest | **240/240 通过；基线 234，新增 6 组** |
| 分层检查 | 119 objects；1361 symbol references；0 inverse symbol/header dependencies |
| 构建开关 | PDF OFF、LCP OFF 的核心共享库编译成功；加密书返回 17，普通 EPUB 正常打开 |

数据：`acceptance.json` 保存公开样本 URL/SHA-256、错误原因及 DLL/probe/font 哈希；`epub-before.json`、`epub-after.json` 保存全部逐页哈希，`epub-after.diff.json` 的 `hash_changed_pages=0`、`needs_review=false`。`ctest.txt` 是最终全量测试原始输出，`verification.json` 记录源码/构建和数字核验。真书及公开书正文未加入仓库。

基线为 `ed252fb6e483192ec0553a936e341f49c144b824`；同一 Windows x64、MinGW GCC、Release，Mbed TLS 3.6.7。两次真书运行使用同一 `tools/regress/run_realbooks.py`、`tools/regress/layout.json` 和 Reader.otf。构建保留 PDF/JPX、音频、书库、全文索引，关闭 ICC、WebP/TIFF/AVIF；这些选项在前后保持一致。

新增 6 组分别为 normal、credentials、expired、unsupported、malformed、lifetime。23 个独立 Python cryptography 生成的小 EPUB 覆盖两种许可证文件名、UTF-8 口令、XML Encryption 任意填充、方法 0/8、空资源、转义路径、日期偏移、畸形 JSON/XML/密文、缺失许可证、源短读和所有预算分配失败点。未改既有测试断言；复跑中发现空 `<encryption/>` 的旧导出测试受影响，已修复读取兼容行为，原断言通过。

**范围**：仅 Basic Profile 资源解码；无 RSA 签名/证书链/CRL 验证，信任校验由宿主负责；商用 profile 1.0/2.x 尚未支持，需要 EDRLab 的生产集成材料。只在打开时检查授权日期，不做 LSD 登记/续借/归还/撤销/到期回收。

**Adobe ADEPT 未支持**：尝试官方样本库 Alice 与 Geography of Bliss 下载，均返回 HTTP 403，未获得授权 EPUB/许可证/用户密钥的完整测试组合。继续实现需要这些材料及无 DRM 对照；设备激活仍不在范围内。来源、复现步骤和 API 细节见 [DRM 说明](../../docs/DRM.md)。

创建 draft PR 后由现有 pull_request 配置自动触发 CI；不改 `.github/`，不调用 workflow_dispatch，不取消 workflow run。
