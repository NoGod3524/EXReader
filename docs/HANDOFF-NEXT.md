# 当前检查点与后续顺序

2026-10-19，C11 SDK **3.35.1**，MIT，ABI1，schema6。分支 `codex/framework`。
核心与PDF读取3.35.1，其余组件3.33.0。完整工作范围为WP1–WP16，包含4a、12a。
目标和量化出口保留在[开发路线](HANDOFF.md)，历史编号见[更新日志](../CHANGELOG.md)。

## 1. 当前验证

- 本地GCC16.2、MSVC Release各140/140；ICC-OFF专项8/8。
- 安装静态组件4/4，13个模块头独立C++编译；EXACT C++实际运行3.35.1 ABI1。
- 703项公开布局逐行保持，两个DLL均305导出；分层99对象/1035符号引用/899本地include，逆向0。
- 本批[原始记录](validation/2026-10-19-coverage.json)，完整[验证历史](NATIVE_VALIDATION.md)。
- 3.34.2代码`7a60f36f8a5f8ec336c4b6e22c695494a41b0074`的[CI39342750378](https://github.com/NoGod3524/EXReader/actions/runs/39342750378)7/7成功：三桌面各139/139，sanitizer136/136，20万次变异无崩溃；[作业记录](validation/2026-10-19-mask-scope-ci.json)。该结果不代替3.35.x的CI。
- 3.35.0代码`04f7e7be1131e7adcd17b67b578bae5c07abdd86`的[CI39343939083](https://github.com/NoGod3524/EXReader/actions/runs/39343939083)需单独记录最终结果。

## 2. 快速验证

已有ASCII源码junction `C:/Users/Oscar/exr`，依赖缓存`C:/Users/Oscar/exr-deps`。

```powershell
cmake --build C:/Users/Oscar/exr-build --config Release --parallel 6
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure

cmake --build C:/Users/Oscar/exr-gcc --parallel 6
ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure
```

当前完整配置两边均预期140项，测试数随裁剪与工具配置变化。
关闭ICC使用`-DEXR_ENABLE_ICC=OFF`，回到已声明的朴素DeviceCMYK换算。
安装与移动设备验收分别记录，交叉编译不替代真机运行。

## 3. 最近已落地的修复

- 默认完整CMYK ICC按需解压；原始961,644字节，zlib414,609字节。RGB普通路径不初始化，[来源与哈希](../src/profiles/README.md)。
- 3.34.0：DeviceCMYK图像和2–7型渐变保留原生墨色，75份原创PDF，MuPDF原生CMYK对照63场景最大差2/255；[分色记录](validation/2026-10-19-native-inks.json)。
- 3.34.1：修正非隔离/挖空源alpha与背景移除，128份嵌套场景；24组区域/整图逐字节一致，工作分配至少降低97%，1000次scope内存恒定；[记录](validation/2026-10-19-nested-groups.json)。
- 3.34.2：SMask缺省保留、透明Form内外单次应用、子组独立shape；27场景+3错误输入；[记录](validation/2026-10-19-mask-scope.json)。
- 3.35.0：Identity及Type 0/2/3/4 TR、Domain/Range、真实变换BBox、G的K/I与BC参与混合；72场景+8错误输入，576个通道最大差0；[记录](validation/2026-10-19-mask-functions.json)。
- 3.35.1：CMYK路径和图像矩形采样覆盖与透明度分离，48组合回归；活跃mask结果预算跨递归G共享并预留，超限/取消/失败清理回归。64MiB仅指mask结果载荷，不是全进程总内存。

## 4. 未关闭项

- WP1/WP2：AIS，图像固有shape与mask/opacity，零opacity在挖空中的行为，更多组色空间和全部组合矩阵。
- 外部差异：低alpha嵌套、可见色键与图形状态mask、画布外反相mask、非隔离亮度组等；[规范与对照口径](MASK_SEMANTICS.md)。不能以内部探针吻合替代外部兼容。
- WP4：ICCBased/DeviceN到组空间、OutputIntent、其他ICC/图像与印刷色彩矩阵。
- 渐变Extend/Domain/BBox/Background、WP4a的PubSec/EFOpen/加密写回/JPX/JBIG2/Pattern，以及全库安全审计。
- WP5–WP16仍按开发路线逐包交付。移动真机、授权LCP出版物和每fuzz目标24 CPU小时的验收尚未完成。

## 5. 后续顺序

1. 收齐当前批次CI；继续AIS和图像shape/opacity。先冻结按规范独立计算的预乘/白底探针，再实现开放绘制状态与PDF映射；包装sink完整转发，保留旧前缀与公开记录布局。
2. 回到渐变Extend/Domain/BBox/Background；ICCBased/DeviceN、OutputIntent按WP4矩阵逐项验收。
3. WP4a按PubSec、EFOpen、加密写回、JBIG2、JPX、Pattern分别冻结范围。认证项各至少10个凭据/损坏/权限/取消输入；图像/绘制项各至少3正例、2反例。
4. 继续[开发路线](HANDOFF.md)的全部WP5–WP16（含12a），保留已有通过项及每次失败回归。

版本按更新规模分配：超大升主版本，中等升次版本，小缺陷修复升补丁，同批不逐条编号。
公开接口和所有权遵循[SDK兼容说明](SDK_COMPATIBILITY.md)。原容差不扩大，原始性能与失败记录保留。
