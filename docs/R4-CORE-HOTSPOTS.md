# R4 核心热点定位

起点为 `9bd2b2c3caf1f63dc4437e0af978247494e87145`，SDK 保护基线为 `9c69bc4c7efb0cff68ced27562709fe597189041`。
原始定位阶段未修改引擎。其后已完成锚点候选的同条件比较和 CMap 修复；后文逐项记录受测源码与范围。

首个定位候选是 `src/anchor.c` 的 KMP 搜索与有界 `exr_doc_span()` 取文调用链。
此前宿主已记录长章点锚解析达到取消期限，但尚未证明热点归因。
`.github/workflows/r4-core.yml` 在原始起点单独构建安装 SDK，以公开接口测 1/4 MiB 单章、16 KiB/4 MiB 窗口的点与引文恢复。
每次新进程，固定字体和页参数，三份 Release 样本；另以独立 `-pg` 构建收集 gprof，不能把插桩数字当作正式性能基线。

复用已有有界语料生成器，不修改 R2/R3 工具。保留每次 stdout/stderr、退出状态、输入/字体/消费者散列、源码和构建身份。
探针记录恢复前后窗口加载、耗时、独立快照参考的匹配状态以及恢复前第一页/恢复后第二页的源范围与完整 RGBA 一致性。
有界峰值 RSS 在创建独立快照前读取；解析统计保留索引/工作区/显式快照，整个进程 RSS 不冒充解析工作区。
每次恢复使用 30 秒取消期限，进程外 120 秒；失败不筛掉。共享 runner 磁盘缓存未控制，没有硬预算。

仅当云端定位显示可重现热点，才在根代理协调下修改最小公共调用点，并保存同条件前后、取消/预算和 ASan 回归。
首轮定位和后继锚点候选均已在云端完成。

## 原始基线定位

工具源码 `7f869d6e21baccb5e7dc4ed6217ad3b06be30f77`，engine 固定原始 `9bd2b2c3caf1f63dc4437e0af978247494e87145`。
run `39887271156` 两作业全部成功，Release job `120198255459`，gprof job `120198255757`。
12 个 Release 新进程和 1 个插桩新进程全部匹配独立快照的 selector、结果及两页完整 RGBA，失败 0。

| 合成场景 | 恢复中位 ms | 恢复窗口加载 | peak workspace bytes |
| --- | ---: | ---: | ---: |
| 1 MiB，16 KiB 窗，点 | 799.598170 | 129 | 2282106 |
| 4 MiB，16 KiB 窗，点 | 11993.697595 | 519 | 2404622 |
| 4 MiB，4 MiB 窗，点 | 184.916612 | 0 | 17894835 |
| 4 MiB，16 KiB 窗，64 字节引文 | 5977.935286 | 259 | 2404622 |

gprof 平面采样：ZIP CRC 46.90%，XML tokenizer/update 38.53%，`text_view` 1.17%。
主成本为扫描反复加载窗口后的 ZIP/XML 重读，不以逐字节派发为由重写 span 或加缓存。
所有恢复结果为合法 `AMBIGUOUS`；这只复现重复正文锚点的瓶颈，不代表真实书整体性能。

Release 工件 `12472493865`，3086263 B，digest `sha256:6f0245df89d4cb52c66244b2e047fc720a1530d8f63036e9a62e8c720d08add7`。
gprof 工件 `12473620800`，3145238 B，digest `sha256:b82d225f3079235e3a929382ff9c2371373876a3e2f3e8b33ea161171125a258`。
原始约 12 秒样本和全部原件保留，后继不改其输入、窗口或资源上限。

## 不可逆歧义候选

`candidate()` 的分数仅为完整 prefix 和 suffix 各加 1，故全局上限为 2。
一旦两个不同位置都得 2 分，任何后续候选最高只能与它们同分；`tied` 不可能被更高分清除。
公共 `search()` 可在此状态终止，并保留取消检查。1 分的平局仍须继续寻找迟出现的 2 分唯一候选。
共享路径覆盖普通正文、固定页长度限定正文、书库重定位和有界 pager；跨章同路径亦不改变上限。
不修改源投影、页面布局、窗口预算、API/ABI/schema 或 sink 的完成/失败语义。

后继工作流在同一 runner 交替运行原始/候选新进程，各场景各三对，双方使用同一探针、语料、字体、Release 参数。
每对匹配状态、正文长度及页面散列须相同；每场景恢复中位比率须小于 0.25，解析 workspace 不增，RSS 允许 5% 加 1 MiB 的进程噪声，消费者最多增加 4096 B。
另运行双方原生 anchor/fixed-text/chapter/CFI 及专属跨 scope/迟高分/点/取消回归；候选全量原生回归再跑 ASan/UBSan。
未通过这些同次检查前，不授予优化通过。

Android 宿主用例固定要求真实 5 秒超时。源码复查确认 `Large.epub` 由 SHA 链 PRNG 产生唯一上下文，并非重复正文的歧义夹具；保留原夹具和 5000 ms 断言，在新核心上复验。
旧 SDK 冻结及宿主通过不授予新核心；重新冻结和宿主复验由集成人协调。

首个候选 `254ea8b` / run `39888168960` 未通过，完整原件保留。
专属测试错误地用公开 constructor 创建重复 chapter path，原始基线即按契约拒绝，未执行 A/B 采样。
改为合法不同 path 的跨章全局搜索；重复 spine path 继续由不改动的原始 `test_anchor.c` 覆盖。
同时确认 reading preset 的裁剪配置只注册少量原生组件测试；后继直接把原始 public anchor/fixed-text 测试链接双方已安装 core，候选 sanitizer 使用完整原生配置注册全套（含 chapter/CFI）。

## 锚点候选与 CMap 的已核结果

`c9ddc74c10959a97f3f831aa08079b643f9d50ec` / run `39888656038` 保留失败：
完整 sanitizer 测试的 fixed-text 断言 143 检出短搜索增加了一次取消轮询。
`84e5db9af496aa9162e65fa04204874b07ce89c8` 删除提前返回路径新增的轮询，保留原断言与原循环的取消检查；run `39890249928` 两作业通过。

CMap 独立核心提交 `193317baa7fe3ae14e318d9f81daa911a7b72cf4` 仅在字体明确单字节时处理 Adobe simple-font ToUnicode 的单个完整两字节 codespace：
将其归一为单字节；两字节零填充源码必须不大于 255。
严格 CMap 入口不变；多 codespace、范围越界、归一后冲突、非法 UTF-16 均拒绝。
真实原始 streams 的结构诊断 run `39890250161`，工件 `12473769918`，digest `sha256:09eb145c962ce8e09aeac43511c043d8346ef8234bb6263655287090de775257`。

受测 `193317b` 的 run `39890468939` 两作业终态均为 success：
Release 比较 job `120208720164`，ASan/UBSan job `120208720476`。
候选全部 160 个原生测试及 3 个独立公开接口回归通过；双方另各过 1 个 native-anchor-boundary 和 3 个公开接口回归。

| 同次交替新进程场景，各三对 | 原始恢复中位 ms | 候选恢复中位 ms | workspace bytes（双方相同） |
| --- | ---: | ---: | ---: |
| 1 MiB，16 KiB 窗，点 | 803.609534 | 0.017633 | 2282106 |
| 4 MiB，16 KiB 窗，点 | 12054.200135 | 0.017734 | 2404622 |
| 4 MiB，4 MiB 窗，点 | 184.382715 | 0.019116 | 17894835 |
| 4 MiB，16 KiB 窗，64 字节引文 | 6044.167324 | 0.020538 | 2404622 |

12 对结果的匹配状态、正文长度、恢复前后两页完整 RGBA 散列相同，均为合法 AMBIGUOUS；所有场景同次比率、workspace、RSS、体积条件通过，`optimization_accepted=true`。
4 MiB 小窗点恢复的窗口加载从 519 降至 0，引文从 259 降至 0；消费者双方均为 6618176 B。
RSS 中位数 1 MiB 场景双方 26632192 B，其余双方 51798016 B；共享 runner 磁盘缓存仍未控制。
此结论适用上述重复正文的不可逆最大分歧义；不推广为唯一/缺失锚点或真实整书整体提速。

| `39890468939` 工件 | ID | bytes | SHA-256 digest |
| --- | --- | ---: | --- |
| comparison | 12473814128 | 8841228 | `01be5ecd1ea3ff7d5fe19f2d7ee912ef46e6c18f278f4af604603257d6835e69` |
| sanitizer | 12475190625 | 20382 | `913c9a1a79e73afdc51b25356b650820078d598fe77961e5e1621d5ec76b8995` |

两次早期失败也全部留存，未以通过样本替换：

| run / 源码 | comparison 工件 / digest | sanitizer 工件 / digest |
| --- | --- | --- |
| 39888168960 / 254ea8b | 12473203685 / `31cb29476d1d97f664a3e4ded5366df24682b66fe3f0f40c06dd84cdbf61389f` | 12474060018 / `358c9ea0e1120ef31caaa12f24ee142251313bb15f6af0fee38a4e35e770e43e` |
| 39888656038 / c9ddc74 | 12474200488 / `954939bd9022018a34d0e0cc225f56f84a8c2ffafe6f74ac646ed0f75be25887` | 12473504274 / `d4b14720a25006e19cc77a3550c7ee17093934cc1a0d90cced95b160294ea069` |

## 真实 PDF 失败链

两份真实 PDF 使用已登记的 `ea5c13e081cfba86d9f6dd759439894463e51126` 语料身份及固定工具 `232a1806c38e0775892da2b4dd82fe6cd90414b2`。
每个全页/独立重开定位进程保持原 120 秒限制；输入在运行前后核对 SHA-256。
CSF2 为 `3c31f46fee98cac0c4323453e5109291a213b4de7fef8c058af9bf67f717433c`（32 页），NASA 为 `2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a`（42 页）。

`9ec1e53cb0f9cf730e4c3ac3fac0414c2769264e` / run `39891075765`：CSF2 全 32 页与 32 页独立重开定位通过；NASA 42 页独立重开定位通过，首页 render 返回 EXR_UNSUPPORTED（11），全文流程失败。
原失败工件 `12474886324`，40666625 B，digest `sha256:b25abd739515fd477fe28624920e7ea83de3d0f8a362b654a4fe7bdbc13aba18`。
run `39891664677` 在云端读取该原工件 stderr，确认具体拒绝为 `PDF soft mask group colour space is not device RGB or grey`，同源码诊断重跑也保留失败。

结构诊断 `20700c2c60a20d5f89271c94e264b72e3f79bda0` / run `39891790701` 的 job `120213017707` 逐组核对 NASA 实际 CS，均为 DeviceCMYK；CSF2 为 DeviceRGB。
工件 `12475301191`，digest `sha256:1687f3f72dbeeac372ab3d471412403276a218716b7a1aa075858f6c29a4e1f1`，原 PDF 和原始 CMap 不改写。

后继软蒙版候选 `80a1c7282033b92ade0e46242ce0e086e6374cdf` 与 `410b285`：
仅放行既有渲染器支持的 DeviceCMYK，并传递 CMYK 组标志，复用墨色混合与 ICC 转换；未放行 ICCBased/Cal 等任意 CS。
CMYK Luminosity 默认 BC 按色彩空间初始黑色 `[0 0 0 1]` 转换，显式 BC 必须为四分量；显式 `[0 0 0 0]` 为白色，分别核对。
依据 [Adobe PDF 1.7 §7.5 Table 7.10，第 553 页](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf)，默认值是该色彩空间的初始黑色；`410b285` 对全零默认的中间预期已在 `db9ab64` 修正，不授予错误预期通过。
现有 `test_pdf_groupcs.c` 增加内存 PDF，独立 LittleCMS 参考核对重叠半透明 CMYK 的 Alpha/Luminosity、BC4 与错误 BC3 拒绝。
其受测终态在后续记录中单独列出；以上锚点通过不授予软蒙版候选或 R2 八份整包通过。

`db9ab643f8435caf33a673ff48817748387a8f76` 仅容忍父 consumer 明确报告 CMYK 的非隔离子组重复 CMYK 声明，其他非隔离异空间仍拒绝。
此为 Adobe 文件的兼容容错：PDF 1.7 §7.6.2 要求非隔离组继承父空间；同空间声明不改变该继承，也不发生色彩空间转换。
run `39892414824` 的原字典与 SMask 关系记录在云端 job `120215013245`；工件 `12475143202`，digest `sha256:0066c59684a566011025d3eb9238298580229a0c2025a9e30d8acccca8ce8081`。

其后 NASA 首 render 暴露反序的软蒙版 BBox。
run `39893052882` / job `120217030750` 读取原 `SMask /G 3386 0 R` 的 BBox `[25.4496 463.157 828.97 350.837]`，Y 角反序；原文件不改写。
`94a318ddfa09782ccf3a6bd344fc8bf6d47352a4` 对软蒙版使用普通 Form 既有的反序角标准化规则；原 `softmask-bad-7.pdf` 保留并核对全绿正例，其他七个坏字典继续拒绝。

`a221c1c24c8990276aa185f559ac6a37a4ffba8c` 将 CMYK Luminosity 的 BC 复合放到 CMYK 父层中，再进行非线性 ICC 转换；内部 `background_cmyk` 只在同步调用中借用。
普通渲染路径不增加图层，CMYK Luminosity 使用原 canvas 的层数、64 MiB 字节预算、work 与取消检查。
独立参考先按墨色值合成半透明组与 BC，再独立 LittleCMS 转换为亮度；覆盖默认黑、显式白、显式彩色 BC、Alpha、opaque、非隔离同空间及异空间拒绝，另核一字节 mask 预算和取消失败无输出。
受测 `026b360750d6514695f6ef02d634c08e21285903` 的 run `39893173638` / job `120217407136`，pdf-groupcs、mask-scope、mask-functions、blend 四套 Release 参考通过。
工件 `12475622632`，1843 B，digest `sha256:de7cbad0d49894d237f5185408b4c553988f78d199f83e5ded8bb85b1a70d62d`；反序 BBox 后继另测。

真实 PDF 中间失败原件全部保留：

| run / 源码 | NASA full 首失败 | 工件 / SHA-256 digest |
| --- | --- | --- |
| 39891664677 / de6e7c9 | EXR_UNSUPPORTED，软蒙版 CMYK | 12475366020 / `7756550d580e3165985079bcf8f26804c0c387b473819d6b8382ca81e68a2b62` |
| 39892070562 / 80a1c72 | EXR_FORMAT，非隔离组显式 CS | 12474209768 / `2dd5a2e883f0f065d18b52aff00856d1b94ce42e1ce4dcffeeae55aee42a9931` |
| 39892182206 / 410b285 | EXR_FORMAT，非隔离组显式 CS | 12475670359 / `7c0dc96061cb91bf16ac25b9e22067d8b38e2005bcb8ab1d04bdfab34822d41d` |
| 39892632755 / db9ab64 | EXR_FORMAT，反序 BBox | 12474758943 / `772d549285aee87aff8f90c166ee68afe1377de599ae68e9d07c4bfe0ebda3df` |
| 39892953377 / a221c1c | EXR_FORMAT，反序 BBox | 12474809050 / `6874f561f411bfc3ce0636c27e7326002d7fa5cc77fb1cfe44889076d6bc20df` |
| 39892992573 / 64c7000 | EXR_FORMAT，反序 BBox | 12475337323 / `d429f6dc951d7669f25f8637d8eaecc164b4cdd5245c9dcf234cb53aab169a73` |

`94a318d` 的完整 run `39893258710` 两作业通过（包括 160 原生 + 3 专属 ASan/UBSan）；另 run `39893258736` 四套独立 Release 参考通过。
sanitizer 工件 `12475619627` / `sha256:98082861b91cedef21375fbda510d01bac759c43fbd3ab72c854042a5424bc90`，comparison 工件 `12475324323` / `sha256:58ac0938bca32b06b886d38ecf4e1a288ba47dc7d77b91724d9f697dd4d33ffe`。
NASA 真实 run `39893258513` 完成前 4 页后，page 4 render 以 EXR_LIMIT（6）拒绝，stderr 为 `Paint source work budget exceeded`；42 页定位仍通过。
原件 `12475861168`，40667645 B，digest `sha256:3fe4e167abe5321a4351d713772aa3ee510b480b5959ced20daf51f883896ab3`。

## 裁剪内实际采样的 work 记账

源码追踪 `exr_canvas_paint()`：旧实现每行先按整张 bitmap 的像素数收取昂贵采样/复合成本，随后才对 coverage 为零的像素跳过。
`7e4bda7306910811878fca8a56045fd6e0728f3a` 保留逐行完整 clip 扫描成本，确定非零 coverage 的首尾 span 与数量，额外收 span 内检查成本，采样/复合成本只按实际非零像素收取。
绘制循环缩到该 span；有洞的 clip 仍逐像素检查，零 alpha、knockout shape、奇异矩阵、取消和无 clip 路径不改。
原 256 MiB work、图层和 mask 预算未提高。

受测 `9874cab1a193c25d8bbf38add0c28fc0f638c354`，同 runner run `39893977844`：
job `120219993744` 的 pdf-groupcs、mask-scope、mask-functions、blend、paint-source 五套参考通过；job `120219993306` 在固定 `94a318d` 原始 SDK 与候选之间交替运行三对新进程。
3072² 画布的小矩形有洞 clip 双方均实际调用 sampler 48 次，working pixel hash 均为 `861f4780274ac3cb`。
旧实现空行扫描过程中提前 LIMIT，候选完成所有行并成功；失败 working memory 散列仅为内部诊断，不冒充旧实现发布过完整输出。

| 三对新进程中位 | 原始 | 候选 |
| --- | ---: | ---: |
| 小 clip+洞，status | LIMIT (6) | OK (0) |
| 小 clip+洞，charged work | 268369920 | 9437776 |
| 小 clip+洞，sampler calls | 48 | 48 |
| 小 clip+洞，paint CPU ms | 6.599 | 8.345 |
| 整页复杂源，status | LIMIT (6) | LIMIT (6) |
| 整页复杂源，charged work | 268369920 | 268369920 |
| 整页复杂源，sampler calls | 22364160 | 22364160 |
| 整页复杂源，paint CPU ms | 471.895 | 451.097 |

小 clip 的候选完成整幅扫描，原始提前失败，CPU 不是等量完成工作的速度比较；本项授予 work 正确记账与完整结果，不宣称小 clip 提速。
整页负控仍拒绝，working hash 均为 `9f970139dd772383`。
work 工件 `12476017226`，3278 B，digest `sha256:7936403fa57bc4727c686316b4c32381d0faab396f22432e3bf4811f42ca97ff`；reference 工件 `12476046054`，2266 B，digest `sha256:bfcdfa8a2417df36499ebc24482731e812ce48a23bd7d27bb3dbfd109dbff254`。

真实 run `39893872332` 在 `7e4bda7` 完成 NASA 前 29 页、提取 96481 字节，约 9.5 秒后 page 29 render 报 `Invalid PDF font CID`（EXR_FORMAT，5）；CSF2 32 页完整流程和两份独立重开定位仍通过。
原件 `12475971915`，40667824 B，digest `sha256:0ba2dbe55bcb1876f7dd907a2ac459877b732a0ae5bb1d1d753d79fb70fb4556`。
`9874cab` 的 real run `39894005219` 在重新采集 NASA 时遇到 HTTP 429，未执行引擎；工件 `12476146430` 保留采集失败，不记为引擎结果。
后继 real workflow 复用已保留的 `12474886324` 原始输入工件，在 CI 内解包并重新核对登记 SHA；不再重复请求原网站。

复用原件的 run `39894262970`（`b313b33`）复现相同 page 29 CID 错误，原件 `12475877362` / `sha256:f58d10c651267d99857e2333fa684edb995aa30f2e0c14d35df4cc323d18efcd`。
429 采集失败工件的 digest 为 `sha256:a05f77649e5c0af94fd73b30c2f7498fc76224d2791a6f9bae370799b4c1612d`。
中间 `a221c1c` 的 sanitizer run `39892953299` 编译失败：新增测试误写 `exr_control.cancel`，正确成员为 `cancelled`，已在 `64c7000` 修复；失败原日志 job `120216711367` 保留。
该次 compilation 未产生 sanitizer XML，不记为 sanitizer 测试执行或通过；同次 comparison 工件 `12475154577` / `sha256:29d75eb432b3df6ed7d5ba14d92728041d73e58f485a2fb49f156b02873226e1` 保留。

## 裸 CID CFF 与 SFNT 包装的实际加载语义

`682aa9aa9baef5ba3ddf61e348b5aef6e09edbf6` / run `39894717532`，job `120222365993` 使用项目实际 bundled FreeType，未用宿主替代库。
原 NASA page 29 的字体 xref 820 为 `BWQAJY+HelveticaNeueLT-Roman`，Type0 / Identity-H；提取程序 SHA-256 为 `93ed0b00cd2b308272134f7833e69a9417b755ff39ce52d588a796303f0bb70b`。

| 同次实际 FreeType 探针 | CID_KEYED / SFNT | num_glyphs | CID42 与内部 GID2 |
| --- | --- | ---: | --- |
| 原 NASA 裸 CFF | 1 / 0 | 213 | 内部 GID 枚举到 73 即 Invalid_Argument；数值并非连续 GID 数 |
| 既有 `pdf-cid.otf` | 0 / 1 | 5 | CID42 不能直接加载；GID2 正确加载三点轮廓 |
| 从同一既有 OTF 提取的裸 CFF | 1 / 0 | 100 | CID42 正确加载三点轮廓；GID2 无效，GID 查询到 5 即 Invalid_Argument |

诊断工件 `12476845099`，6989 B，digest `sha256:0d6ef4e01ded5d29798e3b86f0d418e98c344c3c3f5d7e055fc057a6389f3623`，包含原提取程序与全部 stdout/stderr。
[FreeType Face Creation 的 CID_KEYED 定义](https://freetype.org/freetype2/docs/reference/ft2-face_creation.html) 明确裸 CID 字体使用 CID 加载，SFNT 包装使用连续 GID；裸字体的 `num_glyphs` 对应 CID 范围。

候选 `863574a1e3cff31d4bd356e4d76c0be5609b835e` 仅对实际 `FT_IS_CID_KEYED` 分支直接用 CID 加载，不枚举并猜测错误终点；SFNT 仍保留原 CID→GID 表。
裸字体不存在的子集 CID 仅在 FreeType 返回 Invalid_Argument 时映射到 `.notdef`，其他加载错误继续拒绝；越范围 CID 也按原规则映射 `.notdef`。
裸分支增加一次实际 glyph 加载以区分缺失 CID；正式 R3 性能测量须使用包含这一成本的集成源码。
现有 `native-pdf-outline` 保留包装字体 GID2 的全部轮廓断言，另从既有 OTF 在测试进程内提取裸 CFF 并构造合法 PDF，核 CID42、相同轮廓与缺失 CID2/65535。
这些夹具和诊断均只在 GitHub Actions 生成和运行。

`863574a` 同源 run `39894961912` 的六套 Release 参考通过（新增 pdf-outline），三对交替新进程 work 比较通过。
最终 paint CPU 中位 ms：整页原始 471.824、候选 451.547；小 clip 原始提前 LIMIT 6.619、候选完成 9.235，采样次数、work 与 working hash 结论同上。
reference 工件 `12476472052`，2355 B，digest `sha256:483124b34dc232dd1cf029601bf849e6288395ce99b3165781252b920617c14c`；work 工件 `12476815972`，3281 B，digest `sha256:4818829e0c8893396a09295a0c26bd67a158b530433c8d88d6d23fe73f53eb95`。
同源 anchor comparison job `120223138114` 通过，工件 `12476855942`，8841603 B，digest `sha256:05fa8a9a64aad8f19dbb40e34ca9f41916c7181990dc5a54c6103a532472da0e`。
同源完整 ASan+UBSan job `120223138331` 最终通过：160 个 native 测试与 3 个独立 anchor 测试均成功；工件 `12476945853`，20697 B，digest `sha256:80342874f4c6d69eba176907720867a51c35399f1a1580af3ea847d08b195270`。

同源真实 run `39894961434`：CSF2 全 32 页流程与 32 页重开定位通过；NASA 42 页重开定位通过，全文完成前 35 页、提取 115360 字节，约 11.5 秒后 page 35 render 返回 EXR_FORMAT。
stderr 为 `PDF stream filter or parameter shape is not implemented`，未更改原 120 秒或资源预算。
原件 `12476157175`，40668070 B，digest `sha256:8fd2569aece8e9941585a313437d54433c2862e44b4bc9c9efcea00529c7580b`。

主代理接管该过滤器失败；R4 没有改写 `pdf_objects.c`。
纯结构诊断提交 `a346f1201c7d8df6fd6386cf0cd675e149d5882d` / run `39895458104`，job `120224731689` 只在 CI 内读取保留的原件，没有编译或执行引擎。
page 35 的 page xref 为 351，Contents 352 使用 FlateDecode；唯一图像 `/Im0` xref 357 使用 JPXDecode、Indexed 色彩空间 845 0 R、Decode `[0 255]`，8-bit、575×288、Length 45650，无 DecodeParms。
全文件扫描只找到这一项不受支持过滤器候选；原件 SHA 仍为 `2280fa3e302774d2681a98ba5ff33e7dc3bc63440d13b01453ec1bda36f32b5a`。
stream 诊断工件 `12476915870`，922 B，digest `sha256:b036557786b831e1272e995d5739b0b0160ef817c6ef038aae7e884ad53537e6`。

本分支的真实两 PDF 仍保留一次未通过，不能记为 NASA 全 42 页通过、R2 八份整包通过、历史 1710 目标通过，或新 SDK/宿主授予；后续集成源码须由主代理重新核对。

## JPX 原组件解码与集成边界

`400d825` 至 `1a1d6e5` 新增 `src/pdf_jpx.c` / `pdf_jpx_internal.h`，仅返回逐行补齐、MSB-first 的原组件样本；Indexed 不在 OpenJPEG 内转 RGB。
主代理维护终端过滤器与 `pdf_image.c`，R2 维护主 CMake、依赖与许可证，R3 维护 public SDK 集成对照。
解码器使用 R2 固定 OpenJPEG 2.5.4，archive SHA-256 `a695fbe19c0165f295a8531b1e4e855cd94d0875d2f88ec4b61080677e27188a`。
明确 PDF 色彩空间、1/2/4/8/16-bit 无符号组件、相同完整尺寸且无子采样可进入解码；其他布局、CDEF/内嵌 alpha，以及非 Indexed 的 PCLR/CMAP 拒绝。
`opj_read_header` 后验证完整几何、组件精度和符号，再执行 `opj_decode`；packed 单独不超过 64 MiB，32-bit 组件平面与 packed 合计不超过 64 MiB。
父级继续在 128 MiB image_chain 中计入本图 RGBA、组件平面与 packed，解码返回后释放平面计数；这里的可见样本内存计数不包含 OpenJPEG 内部工作区。
内存流 read/skip/seek 检查边界，strict mode 拒绝截断；失败输出始终 NULL/0，并覆盖预取消及读取压缩数据期间取消。
`1a1d6e5` 明确零 worker 只用调用线程；实际 thread support 时设置 0，`MUTEX_stub` 本身已无线程且其 `set_threads` 返回 false，因此不调用它。
关闭 `EXR_ENABLE_PDF_JPX` 后只保留无 OpenJPEG include/link 的 EXR_UNSUPPORTED stub。

规范在 Actions 内下载官方 [PDF Reference 1.7](https://opensource.adobe.com/dc-acrobat-sdk-docs/pdfstandards/pdfreference1.7old.pdf) 并提取原文，SHA-256 `4aa598e7e2cc88867565fae793db38c140a10ca2b5551dccdb45e2124282ce29`。
run `39896660928` / job `120228578772` 保存 86–90、340–346 页全文；§3.3.8 页 89：

> Decode is ignored, except in the case where the image is treated as a mask; that is, when ImageMask is true. In this case, the JPEG2000 data must provide a single color channel with 1-bit samples.

Table 4.39 页 341 独立写明：

> If the image uses the JPXDecode filter and ImageMask is false, Decode is ignored.

页 89 允许 Indexed 且限制 256 色，没有 Decode 例外；主代理据此让非蒙版 Indexed 也忽略显式 Decode。
本轮仅支持明确且与码流一致的 BitsPerComponent；规范允许的省略/覆盖元数据范围不在本次实现内。

最终专属源码 `f4e9da8479c6cfe4b0806ab80de376c68bd89415`，run `39897100291` / decoder job `120229957889` / primary-spec job `120229958124` 全部 success。
独立子项目使用与正式依赖相同的 22 个 C 源、生成配置和 `MUTEX_stub`；ASan+UBSan 的两个 CTest 均通过：原组件 packed 回归，以及完全不链接 OpenJPEG 的 disabled 回归。
packed 回归包含 JP2/裸 J2K × Gray/RGB × 1/2/4/8/16-bit 共 20 组精确样本，逐行 padding、尺寸、截断、资源限制、预取消与解码期间取消、signed/subsampling/CDEF/PCLR 拒绝。
Pillow 11.3.0 独立入口对 Gray/RGB8 的 JP2/J2K 四份原组件逐字节通过；原 NASA xref 357 的 JP2 经 adapter 保持 165600 个索引，与 Pillow 读取所提取裸 codestream 的索引逐字节相同，样本 SHA-256 `1b4225ec777eef03635117a7864c3d8eccde447e0f41b7b8f5ab1dc52e6c9392`。
原 NASA 输入重新核对登记 SHA；解包、提取、生成、编译、执行及对照全部只在 GitHub Actions 完成。
最终工件 `12476978448`，217816 B，digest `sha256:c95536471a3aea5b76d1e3303288035860d6b5b56279835643affd7a29db81be`，保留 CTest 日志、编码夹具、原 NASA 图像及逐字节输出。

保留失败链：`400d825` / run `39896566880` 原组件 sanitizer 通过，但独立 reference 步误用上游 CMake 改写前的 binary 路径而未执行，`7693095` 修正后 run `39896660928` 全通过；`0be75cd` / run `39897019441` 正式 stub 配置的 packed 测试通过，新增 disabled CTest 因 workflow 未构建其 target 而 NotRun，`f4e9da8` 补构建后最终双测试及 reference 全通过。
本节授予组件解码证据；完整 PDF、public SDK、ON/OFF/ASan 与原八件集成终态由主代理记录。
