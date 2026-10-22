# 当前入口与历史检查点

## 当前入口：3.40.0 开发版

2026-10-21，SDK **3.40.0**、核心 **3.39.0**、PDF读取 **3.38.3**，MIT，ABI1/schema6。
当前实现证据对应源码 `635225fe6ceb7759a948a1d8cede0ab18ea1cee9`；
最新范围以 [支持矩阵](SUPPORT_MATRIX.md) 和 [开发路线](HANDOFF.md) 为准。

- WP6独立有界EPUB章阅读已验收；入口、预算和查询见 [章阅读契约](WP6-BOUNDED-READER.md)。
- Windows GCC默认/关闭可选图像解码器（均含fuzz）各169/169；当前源码原生CI七作业通过，Linux ASan/UBSan为159/159。证据见 `docs/validation/2026-10-20-wp6-window-reader.json`、`docs/validation/2026-10-21-png-reliability.json`。
- 默认完整包324个公开命名函数导出，原316个全部保留；WP7八脚本、WP8冻结子集、WP12-lite及WP12a的声明边界见支持矩阵和各包文档。完整WP12、平台嵌入、无障碍与移动真机验收仍未完成。
- Windows/macOS/iPhone模拟器/iPad模拟器已有参考App与自动自检；移动真机安装仍按用户要求暂缓。
- WP16未完成：源码 `635225fe6ceb7759a948a1d8cede0ab18ea1cee9` 的长测39666440519仍待96分片及严格汇总；旧失败与旧源码时长保留为历史，不转移CPU额度。

构建、测试、长测、最终汇总和归档仅在GitHub云端执行；本机不执行本页历史命令，
不启动后台轮询、下载或本地重汇总。云端验收与拒绝条件见 [可靠性交接](RELIABILITY-HANDOFF.md)。

## 历史检查点：2026-10-19 / 3.38.0

以下第1–5节保留当时源码的数字、路径与后续安排；它们不描述3.40.0的当前完成状态。

2026-10-19，C11 SDK **3.38.0**，MIT，ABI1，schema6。分支 `codex/framework`。
核心3.37.0、PDF读取3.38.0，其余组件3.33.0。完整工作范围为WP1–WP16，包含4a、12a。
目标和量化出口保留在[开发路线](HANDOFF.md)，历史编号见[更新日志](../CHANGELOG.md)。

### 1. 当时验证

- 本地GCC16.2、MSVC Release各143项覆盖通过（首次142通过，1处测试初始化修正后复验）；ICC-OFF专项12/12。
- 安装静态组件4/4，13个模块头独立C++编译；EXACT C++实际运行3.38.0 ABI1。
- 703项公开测量中702项保持，sink总大小136→144；旧字段偏移不动，新增source结构24字节。两个DLL均306导出；分层99对象/1050符号引用/901本地include，逆向0。
- 本批[原始记录](validation/2026-10-19-shading-extent.json)，完整[验证历史](NATIVE_VALIDATION.md)。
- 3.34.2代码`7a60f36f8a5f8ec336c4b6e22c695494a41b0074`的[CI39342750378](https://github.com/NoGod3524/EXReader/actions/runs/39342750378)7/7成功：三桌面各139/139，sanitizer136/136，20万次变异无崩溃；[作业记录](validation/2026-10-19-mask-scope-ci.json)。该结果不代替后续版本CI。
- 3.35.0代码`04f7e7be1131e7adcd17b67b578bae5c07abdd86`的[CI39343939083](https://github.com/NoGod3524/EXReader/actions/runs/39343939083)7/7成功：三桌面各140/140，sanitizer137/137；[作业记录](validation/2026-10-19-mask-functions-ci.json)。
- 3.35.1代码`c33e758a39a1e0ac89a80202c0bb3fdd3c6d94a4`的[CI39344775219](https://github.com/NoGod3524/EXReader/actions/runs/39344775219)7/7成功，三桌面各140/140、sanitizer137/137；[作业记录](validation/2026-10-19-coverage-ci.json)。
- 3.36.0普通六场景RGBA散列保持；初次flat/state重画p95超10%，保留原样本后用256次/轮复测，分别1.023/1.029。空画布固定载荷增加648字节，无新像素平面。
- 3.36.0代码`2fb652f489c85acd5942068f7bc181321bc05fbe`的[CI39348054966](https://github.com/NoGod3524/EXReader/actions/runs/39348054966)7/7成功：三桌面各141/141、sanitizer138/138；[作业记录](validation/2026-10-19-alpha-source-ci.json)。
- 3.36.1：GCC/MSVC各141/141；渐变Domain、严格字段校验与共享采样工作预算已修复。[逐场景对照](validation/2026-10-19-shading-domain-reference.json)。
- 3.36.1代码`ca26ce985b775b22a97aca3f431cf34431c496a0`的[CI39349805728](https://github.com/NoGod3524/EXReader/actions/runs/39349805728)7/7成功，三桌面各141/141、sanitizer138/138；[作业记录](validation/2026-10-19-shading-domain-ci.json)。
- 3.36.2：径向最大有效根、先归一化再求根、临时BBox和超大实数的引用试探解析已修复；19场景/30探针/4拒绝，成功与失败均恢复裁剪。[逐场景参考](validation/2026-10-19-shading-geometry-reference.json)。
- 3.36.2的[CI39350915545](https://github.com/NoGod3524/EXReader/actions/runs/39350915545)6/7成功；Ubuntu GCC12的条件输出读取告警使严格编译中止，现用已初始化的局部best根替代，随3.37.0复验。[原始失败记录](validation/2026-10-19-shading-geometry-ci.json)。
- 3.37.0：Type1二维函数渐变、1–7型分量函数数组及共享函数图限界；29正常/29拒绝、262144个原始CMYK像素，61文件重生相同。[逐场景参考](validation/2026-10-19-shading-function-reference.json)。
- 3.37.0代码`62f059786be92003f76515d0ca6d253d524d90a4`的[CI39352336301](https://github.com/NoGod3524/EXReader/actions/runs/39352336301)7/7成功，三桌面各141/141、sanitizer138/138，Ubuntu严格编译通过；[作业记录](validation/2026-10-19-shading-function-ci.json)。
- 3.37.1：按ISO11.4.6保留零opacity的shape，修正路径/图片/复合填描及RGB/CMYK子组；64份PDF、192个公开画布组合，本地2500检查。旧参考中跳过零alpha的假设已修正，原文件及容差保留，新旧各384像素差异有散列记录。[逐场景参考](validation/2026-10-19-zero-opacity-reference.json)。

- 3.37.1代码19958c735e9c4e97dcc6b12465c8b4a57f0b69ee的[CI39354240315](https://github.com/NoGod3524/EXReader/actions/runs/39354240315)7/7成功：三桌面142/142，sanitizer139/139，20万次变异无崩溃；[记录](validation/2026-10-19-zero-opacity-ci.json)。
- 3.38.0：通用paint源与原生轴向/径向完整外推；40份PDF、10,240个Decimal参考像素，272个通用画布检查；旧前缀保留有限位图行为，固定色表及Type1/mesh自适应仍待继续。[独立对照](validation/2026-10-19-shading-extent-reference.json)。

### 2. 历史快速验证命令（不作为当前执行安排）

已有ASCII源码junction `C:/Users/Oscar/exr`，依赖缓存`C:/Users/Oscar/exr-deps`。

```powershell
cmake --build C:/Users/Oscar/exr-build --config Release --parallel 6
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure

cmake --build C:/Users/Oscar/exr-gcc --parallel 6
ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure
```

该检查点完整配置两边均预期143项，测试数随裁剪与工具配置变化。
关闭ICC使用`-DEXR_ENABLE_ICC=OFF`，回到已声明的朴素DeviceCMYK换算。
安装与移动设备验收分别记录，交叉编译不替代真机运行。

### 3. 当时已落地的修复

- 默认完整CMYK ICC按需解压；原始961,644字节，zlib414,609字节。RGB普通路径不初始化，[来源与哈希](../src/profiles/README.md)。
- 3.34.0：DeviceCMYK图像和2–7型渐变保留原生墨色，75份原创PDF，MuPDF原生CMYK对照63场景最大差2/255；[分色记录](validation/2026-10-19-native-inks.json)。
- 3.34.1：修正非隔离/挖空源alpha与背景移除，128份嵌套场景；24组区域/整图逐字节一致，工作分配至少降低97%，1000次scope内存恒定；[记录](validation/2026-10-19-nested-groups.json)。
- 3.34.2：SMask缺省保留、透明Form内外单次应用、子组独立shape；27场景+3错误输入；[记录](validation/2026-10-19-mask-scope.json)。
- 3.35.0：Identity及Type 0/2/3/4 TR、Domain/Range、真实变换BBox、G的K/I与BC参与混合；72场景+8错误输入，576个通道最大差0；[记录](validation/2026-10-19-mask-functions.json)。
- 3.35.1：CMYK路径和图像矩形采样覆盖与透明度分离，48组合回归；活跃mask结果预算跨递归G共享并预留，超限/取消/失败清理回归。64MiB仅指mask结果载荷，不是全进程总内存。

- 3.36.0：新增通用alpha_source尾回调，AIS与图像内在shape/opacity分别进入合成；166份PDF、192个RGB/CMYK公开画布组合；状态恢复、旧前缀和错误回调有回归。

### 4. 当时未关闭项

- WP1/WP2：AIS与图像shape/opacity已接入；零opacity已按11.4.6公式修复，继续更多组色空间、外部差异和全部组合矩阵。
- 外部差异：低alpha嵌套、可见色键与图形状态mask、画布外反相mask、非隔离亮度组等；[规范与对照口径](MASK_SEMANTICS.md)。不能以内部探针吻合替代外部兼容。
- WP4：ICCBased/DeviceN到组空间、OutputIntent、其他ICC/图像与印刷色彩矩阵。
- 旧宿主渐变有限外推/自适应采样、WP4a的PubSec/EFOpen/加密写回/JPX/JBIG2/Pattern，以及全库安全审计。sh操作按规范忽略Background，后续Pattern需单独处理。
- WP5–WP16仍按开发路线逐包交付。移动真机、授权LCP出版物和每fuzz目标24 CPU小时的验收尚未完成。

### 5. 当时后续顺序

1. 收齐当前批次CI；AIS与图片shape/opacity已有166场景及192个公开画布组合，继续对照已记录的外部差异及剩余边界；包装sink完整转发，保留旧前缀与公开记录布局。
2. 渐变Domain/BBox/径向根/函数数组已落地，原生完整Extend已接入，继续自适应采样与旧宿主迁移；ICCBased/DeviceN、OutputIntent按WP4矩阵逐项验收。
3. WP4a按PubSec、EFOpen、加密写回、JBIG2、JPX、Pattern分别冻结范围。认证项各至少10个凭据/损坏/权限/取消输入；图像/绘制项各至少3正例、2反例。
4. 继续[开发路线](HANDOFF.md)的全部WP5–WP16（含12a），保留已有通过项及每次失败回归。

版本按更新规模分配：超大升主版本，中等升次版本，小缺陷修复升补丁，同批不逐条编号。
公开接口和所有权遵循[SDK兼容说明](SDK_COMPATIBILITY.md)。原容差不扩大，原始性能与失败记录保留。
