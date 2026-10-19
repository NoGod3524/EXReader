# 当前检查点与后续顺序

2026-10-19，C11 SDK **3.34.2**，MIT，ABI1，schema6。分支 `codex/framework`。

完整历史及旧/新编号映射见[更新日志](../CHANGELOG.md)。

## 已验证代码

当前3.33.1代码`d0a0b8d3736c9b25ce0cd42d9eeaf67a31cdc4e7`，[CI39334889967](https://github.com/NoGod3524/EXReader/actions/runs/39334889967) **7/7通过**。三桌面各136/136、安装/裁剪/绑定宿主均通过；sanitizer133/133、20万次变异与移动库交叉编译通过。准确计数见[本批CI原始数据](validation/2026-10-19-group-spaces-ci.json)。

`716235e6ab4c5bb944c2e240b6a173289b3ab725`，[CI39328976671](https://github.com/NoGod3524/EXReader/actions/runs/39328976671) **7/7通过**。三桌面各136/136；各平台安装静态组件4/4、纯核心1/1及其安装消费1/1、无音频/PDF书库2/2；ASan/UBSan133/133；移动库编译和20万次变异通过。准确结果见[组件验证数据](validation/2026-10-19-components.json)和[CI原始摘要](validation/2026-10-19-components-ci.json)。该CI验证的是0.19.0分层实现；0.20.0仅更新版本声明和规则，本次GCC重新编译、ABI1/1、安装组件4/4和0.20.0 EXACT C++消费验证通过，见[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。

全历史新编号3.33.0已重新通过本地GCC编译、ABI1/1、安装组件4/4及EXACT包C++消费验证；315个历史提交的归属与版本递增检查通过。记录见[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。

此前渲染/ICC审计代码`55089af`的7项CI通过记录继续保留，不能代替本次分层验证。

## 1. 基线与本次范围

修复前 `8467141` 的 MSVC Release、GCC16.2 完整回归均为 **130/130**。随后审计发现既有测试未覆盖的渲染和内存错误；详见 [审计报告](AUDIT-2026-10-19.md)。新增 `native-render-audit` 后完整集合为131项。当前验证结果见该报告与 [验证记录](NATIVE_VALIDATION.md)。

当前检查点包含：PDF渐变的透明度/混合/遮罩、网格4/5字节填充和类型5对角线、函数插值顺序、减色空间混合与嵌套alpha、组裁剪坐标、灰度图像/遮罩清理、表格double边框扩容引用，以及完整默认CMYK ICC压缩内嵌。

## 2. 快速验证

本机已有 ASCII 源码 junction `C:/Users/Oscar/exr`，依赖缓存 `C:/Users/Oscar/exr-deps`。使用 ASCII 路径避开部分工具的中文 argv 限制。

```powershell
cmake --build C:/Users/Oscar/exr-build --config Release --parallel 8
ctest --test-dir C:/Users/Oscar/exr-build -C Release --output-on-failure

cmake --build C:/Users/Oscar/exr-gcc --parallel 8
ctest --test-dir C:/Users/Oscar/exr-gcc --output-on-failure
```

当前预期两边均为 **139项**。关闭色彩管理的独立构建使用 `-DEXR_ENABLE_ICC=OFF`，不嵌入默认profile，回到已声明的朴素DeviceCMYK转换。安装消费与平台CI结果独立列出，不能以Windows测试代替其他平台执行。

## 3. 默认 CMYK 配置

完整 Argyll public-domain profile，原始961,644字节，zlib414,609字节；运行时按需解压并建立LittleCMS转换，原始缓冲随即释放。RGB普通路径不初始化该配置。来源、哈希和复现命令见 [profile说明](../src/profiles/README.md)。不同于MuPDF的默认SWOP；验证使用相同profile或单独报告配置差异。

## 4. 尚未关闭的审计项

- 显式DeviceRGB隔离子组的颜色切换已修复；本批另修正PDF组K极性，验收与剩余项见末尾记录。
- DeviceCMYK图像/2–7型渐变原生分色已补齐；ICCBased/DeviceN到组空间的分色转换仍待扩展。
- 非隔离/挖空组源alpha、背景移除与逐层坐标已修复，新增128场景；低alpha MuPDF外部差异仍待核验。软遮罩/AIS与组shape需继续审计。
- 嵌套Form/AP裁小已补齐；24组整缓冲像素一致、工作分配至少减少97%、1000轮内存恒定；跨平台sanitizer待本批CI。
- 轴向/径向Extend仍有限外推；Domain/BBox/Background尚需逐项核验。
- 全库安全/格式审计尚未结束；本次已验证范围集中于近期PDF、画布与边框变更。

## 分层整理检查点

公开头、内部头与CMake静态组件已拆分。核心、PDF读取、PDF编辑、音频、书库、索引可分别链接；书库在无音频/PDF时仍支持重排文档。本次分层按全历史新编号归为3.33.0，ABI1；默认总DLL保留304个函数，703项公开记录布局值不变。详见[架构说明](ARCHITECTURE.md)。

依赖检查覆盖实际编译符号和递归本地include；完整99对象/1021引用/898头依赖、纯核心59对象/586引用/505头依赖，逆向均为0。原有131项回归加5项组件回归，共136项；纯核心/安装消费和各平台结果独立记录于[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。本轮还修复了裁剪软遮罩预算与内存报告遗漏，渲染审计现为356检查。

后续先继续下列未关闭审计项。不要将完成组件拆分记作全库审计或完整PDF兼容已完成。

## 5. 后续顺序与验收目标

1. 显式RGB隔离子组与DeviceCMYK图像/渐变原生分色已补齐。继续非隔离/挖空组嵌套、逐层区域缓冲，以及渐变Extend/Domain/BBox；ICCBased/DeviceN与完整印刷色彩仍按WP4矩阵推进。
2. **WP4a**：按PubSec、EFOpen、JBIG2、JPX分别冻结输入矩阵；认证项至少10个凭据/损坏/权限/取消场景，图像项至少3正例/2反例。分别交付，保留现有Standard R2–R6回归。
3. **WP6–WP16**：按 [开发路线](HANDOFF.md) 的量化出口推进；完整阅读SDK、OCR、redaction与手机运行尚未完成。

后续按更新规模递增版本：超大更新升主版本，中等更新升次版本，小 bug 修复升补丁版本；规则见[版本分配](VERSIONING.md)。公开结构体、符号与所有权规则遵循 [SDK兼容说明](SDK_COMPATIBILITY.md)。包装sink必须完整转发回调；ToUnicode维持严格校验；色彩断言按独立转换更新，原容差不扩大。

## 3.33.1本地验收

显式RGB隔离子组切换与PDF K极性已修复；MSVC/GCC各136/136、ICC-OFF3/3、安装组件4/4
与EXACT C++消费通过，组色空间229检查。50场景输入改为K=true，Decimal期望未改。
Java示例取消0.x限制；本批新CI已7/7通过，三桌面JNI实际执行通过。原始证据与剩余项见审计/验证记录。
下一步是CMYK组图像/渐变的原始墨色保真，随后继续未关闭的嵌套与区域缓冲问题。


## 3.34.0分色检查点

新增`exr_canvas_image_cmyk`及sink尾回调`image_cmyk`/`image_space`。旧RGBA图层/bitmap不改布局，
普通RGB页不分配额外墨色图。DeviceCMYK解码保留Decode/Matte后的分量，2–7型渐变保留
求值与插值后的分量；以8位C/M/Y/K采样进入组。75份原创PDF中63个颜色/模式场景经MuPDF
1.28.2原生CMYK独立对照，最大差2/255，详见`validation/2026-10-19-native-inks-mupdf.json`。
新增循环Intent错误传播、128MiB双图缓冲限额、透明像素插值和旧sink前缀回归。
用户确认继续全部WP1–WP16，含4a/12a；本子项完成不关闭整个WP4。

本地GCC/MSVC各137/137、ICC-OFF4/4、安装组件4/4、EXACT C++运行和13头编译通过；
分色913检查，独立CMS参考最大差0。分层99/1025/898无逆向，原ABI仅版本化sink尾增长，
旧304导出保留，新增一函数。证据见`validation/2026-10-19-native-inks.json`。


## 3.34.1本地检查点

代码修正源alpha/完整alpha混淆、复合元素shape替换、子组初始背景与坐标；嵌套Form/AP可裁小。
GCC/MSVC各138/138、ICC-OFF5/5、安装组件4/4、EXACT C++运行和13头编译通过。
6194项新检查；旧50场景golden不变；128场景Decimal最大差1，MuPDF低alpha差异最大11单独保留。
24组裁小/整图逐字节一致、工作分配至少减少97%，1000轮内存恒定，五轮性能调查有原始样本。
703项公开布局保持；核心/PDF3.34.1，其余3.33.0。记录见`validation/2026-10-19-nested-groups.json`。

下一轮优先核验软遮罩与挖空的shape/opacity、AIS，以及透明Form进入时SMask应重置、组提交时应用；
已有临时最小输入证明需要继续核对规范/外部输出。然后回到渐变Extend/Domain/BBox与WP4a。
仍继续全部WP1–WP16（含4a/12a），移动真机、授权LCP及24 CPU小时fuzz的外部验收分别记录。


## 3.34.2：遮罩作用域与组形状修复（2026-10-19）

ExtGState缺省/null的SMask保留当前值，显式None才清除。透明Form内部重置SMask，
外部遮罩在整组提交时应用一次；画布组进入/退出保存、恢复并释放各自遮罩。
组在挖空父级内单独累计几何shape，半像素边缘不再作为全覆盖低opacity替换。
shape平面仅在挖空/shape父级需要时分配，每像素4字节，计入层预算及内存报告。
PDF绘制器存活遮罩聚合限制64MiB；嵌套遮罩共享绘制工作计数，逐行检查取消和预算。

27个正常场景与3个拒绝输入；独立数学探针最大差1/255，3.34.1最大差144/255。
MuPDF1.28.2内部探针最大差5；半覆盖边缘差41单独归类，不扩大内部容差。
GCC/MSVC各139/139、ICC-OFF6/6、安装组件4/4及13头C++独立编译通过；
EXACT C++实际运行3.34.2 ABI1，703项布局逐行不变，两个DLL均305导出。
分层99对象/1026符号引用/898include，无逆向。

AIS、图像shape/opacity与自身mask覆盖图形状态mask仍需审计，WP1/WP2尚未整包关闭。
证据：[汇总](validation/2026-10-19-mask-scope.json)、[逐场景对照](validation/2026-10-19-mask-scope-reference.json)。
