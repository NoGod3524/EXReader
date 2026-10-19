# 当前检查点与后续顺序

2026-10-19，C11 SDK **0.20.0**，MIT，ABI1，schema6。分支 `codex/framework`。

## 已验证代码

`716235e6ab4c5bb944c2e240b6a173289b3ab725`，[CI39328976671](https://github.com/NoGod3524/EXReader/actions/runs/39328976671) **7/7通过**。三桌面各136/136；各平台安装静态组件4/4、纯核心1/1及其安装消费1/1、无音频/PDF书库2/2；ASan/UBSan133/133；移动库编译和20万次变异通过。准确结果见[组件验证数据](validation/2026-10-19-components.json)和[CI原始摘要](validation/2026-10-19-components-ci.json)。该CI验证的是0.19.0分层实现；0.20.0仅更新版本声明和规则，本次GCC重新编译、ABI1/1、安装组件4/4和0.20.0 EXACT C++消费验证通过，见[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。

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

当前预期两边均为 **136项**（原131项及5个组件检查）。关闭色彩管理的独立构建使用 `-DEXR_ENABLE_ICC=OFF`，不嵌入默认profile，回到已声明的朴素DeviceCMYK转换。安装消费与平台CI结果独立列出，不能以Windows测试代替其他平台执行。

## 3. 默认 CMYK 配置

完整 Argyll public-domain profile，原始961,644字节，zlib414,609字节；运行时按需解压并建立LittleCMS转换，原始缓冲随即释放。RGB普通路径不初始化该配置。来源、哈希和复现命令见 [profile说明](../src/profiles/README.md)。不同于MuPDF的默认SWOP；验证使用相同profile或单独报告配置差异。

## 4. 尚未关闭的审计项

- CMYK父组内显式RGB子组尚未正确切换混合空间。
- CMYK组中的图像/渐变经过RGBA，原始墨色分离不保真。
- 非隔离/挖空组更多嵌套组合需独立参考覆盖，现有通过的样本不能证明全部正确。
- 组裁小只用于顶层画布组；多数嵌套Form仍分配完整缓冲。
- 轴向/径向Extend仍有限外推；Domain/BBox/Background尚需逐项核验。
- 全库安全/格式审计尚未结束；本次已验证范围集中于近期PDF、画布与边框变更。

## 分层整理检查点

公开头、内部头与CMake静态组件已拆分。核心、PDF读取、PDF编辑、音频、书库、索引可分别链接；书库在无音频/PDF时仍支持重排文档。本次分层版本为0.20.0，ABI1；默认总DLL保留304个函数，703项公开记录布局值不变。详见[架构说明](ARCHITECTURE.md)。

依赖检查覆盖实际编译符号和递归本地include；完整99对象/1021引用/898头依赖、纯核心59对象/586引用/505头依赖，逆向均为0。原有131项回归加5项组件回归，共136项；纯核心/安装消费和各平台结果独立记录于[NATIVE_VALIDATION.md](NATIVE_VALIDATION.md)。本轮还修复了裁剪软遮罩预算与内存报告遗漏，渲染审计现为356检查。

后续先继续下列未关闭审计项。不要将完成组件拆分记作全库审计或完整PDF兼容已完成。

## 5. 后续顺序与验收目标

1. 对上述未关闭渲染项建立最小复现及独立参考，优先处理显式组色空间、原始墨色保真；覆盖至少3个正例、2个反例，再关闭对应矩阵项。
2. **WP4a**：按PubSec、EFOpen、JBIG2、JPX分别冻结输入矩阵；认证项至少10个凭据/损坏/权限/取消场景，图像项至少3正例/2反例。分别交付，保留现有Standard R2–R6回归。
3. **WP6–WP16**：按 [开发路线](HANDOFF.md) 的量化出口推进；完整阅读SDK、OCR、redaction与手机运行尚未完成。

后续按更新规模递增版本：超大更新升主版本，中等更新升次版本，小 bug 修复升补丁版本；规则见[版本分配](VERSIONING.md)。公开结构体、符号与所有权规则遵循 [SDK兼容说明](SDK_COMPATIBILITY.md)。包装sink必须完整转发回调；ToUnicode维持严格校验；色彩断言按独立转换更新，原容差不扩大。
