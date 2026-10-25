# S09：最终分发许可证与 SBOM 闭包

固定实现起点 `0889f7d1e9a537c6c1b05456547e016b26e1cd85`，分支 `codex/reader-fw-s09`。

本包只**新增清单与检查**：不改任何许可证原件、不改 `tools/check_reading_licenses.py`、不改
`tests/reader_distribution_inventory/` 的生成器，也不产生新的法律或运行结论。

## 1. 复用与新增的边界

| 角色 | 源码 | 本包对它的关系 |
| --- | --- | --- |
| 许可登记（唯一事实源，22 项） | `tools/check_reading_licenses.py` | 只读导入：`COMPONENTS`、`enabled()`、`preset_switches()` |
| 安装清单/依赖/SBOM 生成器 | `tests/reader_distribution_inventory/{inventory,combined,sbom,packages,contract}.py` | 只读导入：按字节复算，不重写它们的断言 |
| 安装探针与消费者 | `tests/reader_distribution_inventory/probe`、`tests/reading_core` | 只读复用，用它们真实的链接行做闭包 |
| **新增：闭包校验** | `tests/reader_final_s09/closure.py` | 从 stage 字节 + 登记表重新推导归属、许可、链接与 SBOM 字段 |
| **新增：原工件认证** | `tests/reader_final_s09/authenticate.py` | 命名工件 → 大小/digest/有效期/run/job 上传日志 | 
| **新增：拒绝回归** | `tests/reader_final_s09/check_closure.py` | 夹具在作业内生成：1 正控 + 34 拒绝 + 4 工件身份拒绝 |

## 2. 闭包定义（四个独立结论，不合并）

```
materials_closed  每一份安装字节都被清单逐字记录（缺失/多出/字节或散列漂移即失败）
licence_closed    登记的每份许可原文按 pin 安装；无未登记许可材料；每个包的材料存在
link_closed       随包归档与系统库按真实链接行的字节划分，互不重叠、不互为冒充
sbom_closed       SPDX/CycloneDX 的每个元素都锚定到这些字节、到登记标识符、到来源
accepted          = 上述四者都没有问题，且没有任何文档宣称运行或法律结论
```

`runtime_accepted`、`legal_conclusion`、`product_granted` 恒为 `false`。

### 2.1 归属（模块 / SDK / 第三方）

安装归档按**文件名本身**归到唯一 owner：

| 形态（`.a` 或 `.lib`） | owner |
| --- | --- |
| `lib/(lib)exr_<layer>` | 首方 SDK（`exreader`） |
| `lib/exreader/libexr_vendor_<name>` | 登记表中 `vendor_files` 含 `<name>` 的组件 |
| `lib/<name>`（上游名副本） | 同上（`libaom`→libaom、`libwebp`→libwebp） |
| `lib/<pkg>`、`lib/lib<pkg>`（组合前缀） | `packages.PACKAGES` 里该包的 id |

零 owner → `archive_unowned`；多 owner → `archive_ambiguous_owner`。

### 2.2 重复库

同一个库身份出现两份及以上（G09 记录为六份上游名副本，闭包以真实 stage 为准逐份枚举）时，闭包**必须**逐份记录
路径、owner、字节与 SHA-256，且两份不得属于不同组件（`archive_duplicate_split_owner`）。
SBOM 若把它们合并成一个文件元素，`spdx_file_missing`/`cdx_file_missing` 会失败。

### 2.3 系统库 vs 随包库

不靠名单猜测，靠字节与登记：

- 链接行从**它自己的捕获输出**重新解析（`raw_output_sha256` 校验），不读生成器给的分类结论；
- 随包 = token 的 basename 就是本安装里的归档；系统 = `-l`、`-Wl,`、`-framework`、`.lib` 等；
- 两侧 family 不得重叠（`link_family_overlap`），系统 token 不得命名任何已安装文件
  （`link_bundled_as_system`），分类与记录的 `distributed_archives`/`system_libraries` 必须逐字一致
  （`link_classification_drift`）；
- 每个随包归档必须在真实链接行上，或被清单显式登记为未引用/上游名副本（`link_bundled_not_linked`）；
- 组合前缀里每个包的登记系统依赖必须被观测到（`link_system_unmet`），沿用 `packages.PACKAGES`。

### 2.4 SPDX 字段与来源引用

| 检查 | 失败码 |
| --- | --- |
| SPDX 2.3 / CC0-1.0 / documentNamespace 含源码 SHA / creationInfo | `spdx_document` |
| 每个安装文件一个元素，SHA-1 与 SHA-256 与复算一致，数量一致 | `spdx_file_missing`/`spdx_file_extra`/`spdx_file_checksum` |
| `packageVerificationCode` 按 7.9.4 由复算 SHA-1 重算 | `spdx_verification_code` |
| SDK 包 `hasFiles` 覆盖全部文件元素，`versionInfo` = 安装头版本 | `spdx_has_files`/`spdx_version_info` |
| 每个 owner 有 `SPDXRef-Package-<id>`，`licenseConcluded`/`licenseDeclared` 与登记表逐字一致 | `spdx_component_missing`/`spdx_licence_concluded`/`spdx_licence_declared` |
| 第三方包 `filesAnalyzed=false` | `spdx_files_analyzed` |
| 来源引用：上游带 pin 的 `sourceInfo` 必须含该 SHA-256；首方必须给出下载地址、包注释或与许可材料的 CONTAINS 边 | `spdx_source_reference` |
| 许可材料与所属包的 CONTAINS 边（组合前缀的自有原文包同样要求） | `spdx_licence_link` |
| 关系目标存在、有 DESCRIBES | `spdx_relationship_target`/`spdx_describes` |
| CycloneDX 1.5：component_id 属性、licenses、purl、文件散列、依赖 ref | `cdx_*` |

## 3. 证据来源（两 source 分开记录）

| 证据 | producer source | verifier source | 说明 |
| --- | --- | --- | --- |
| 真实 stage | 本 run 的 `GITHUB_SHA` | 同一 SHA | `reading-library` 预设构建并安装，本地生成清单后立刻闭包 |
| 认证原工件 | `93d2ad0db2d75af50eddc0843a4da9c7090a15aa`（G09 run 40095313750 attempt 1） | 本 run 的 `GITHUB_SHA` | 命名工件 ID + 大小 + digest + 有效期 + run/job 上传日志绑定后解包 |

`closure.json` 的 `sources`/`verifier` 两个对象分别记录，不合并。消费原工件时**不**把当前分支 HEAD
当作 producer。

## 4. 不授予（`not_granted` 常驻字段）

- 运行结论：闭包只读字节与链接行，从不执行候选二进制；
- 法律结论：标识符来自登记表，不做裁决；
- 产品/Release/tag/签名/公证/商店；
- Android、iOS、Apple 宿主打包与宿主字体；
- 可选包的行为（同步、账号、导入、界面）——只闭包其安装材料。

## 5. 复现

```bash
bash tests/reader_final_s09/check_scope.sh
python3 tests/reader_final_s09/check_closure.py                    # 1 正控 + 34 拒绝 + 4 身份拒绝

# 真实 stage（或任一同构安装）
python3 tools/check_reading_licenses.py reading-library build/reading-library \
        build/reading-library/stage build/reading-library/licenses.json --require-release-ready
python3 tests/reader_distribution_inventory/inventory.py --profile reading-library --platform linux \
        --runner-os Linux --build build/reading-library --stage build/reading-library/stage \
        --licenses build/reading-library/licenses.json --consumer build/reading-consumer/reading-document \
        --probe build/probe/probe --probe-build build/probe --output build/reading-library/inventory
python3 tests/reader_final_s09/closure.py --artifact <含 stage/ 与三份 JSON 的目录> \
        --output build/closure --platform linux --kind sdk --preset reading-library \
        --producer-source-sha \$(git rev-parse HEAD)

# 认证原工件（需要 actions: read）
python3 tests/reader_final_s09/authenticate.py --artifact-id 12560228214 \
        --artifact-name reader-distribution-inventory-linux-core-40095313750-1 \
        --job-name 'inventory (ubuntu-22.04, reading-core)' --run-id 40095313750 --attempt 1 \
        --source-sha 93d2ad0db2d75af50eddc0843a4da9c7090a15aa \
        --extract build/producer/linux-core/artifact --output build/producer/linux-core
```
