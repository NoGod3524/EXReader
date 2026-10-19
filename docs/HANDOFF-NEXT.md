# 当前检查点与后续顺序

2026-10-19，C11 SDK **0.19.0**，MIT，ABI1，schema6。分支 `codex/framework`。

## 已验证代码

`55089af988820c1b3ee68b9853f7f4dac907e757`，[CI39324045389](https://github.com/NoGod3524/EXReader/actions/runs/39324045389) **7/7通过**。三桌面各131/131；ASan/UBSan128/128；移动库编译和20万次变异通过。后续记录提交只修改文档/验证数据，运行库与性能数据各自的SHA见 [验证记录](validation/2026-10-19.json)。

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

当前预期两边均为 **131项**。关闭色彩管理的独立构建使用 `-DEXR_ENABLE_ICC=OFF`，不嵌入默认profile，回到已声明的朴素DeviceCMYK转换。安装消费与平台CI结果独立列出，不能以Windows测试代替其他平台执行。

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

通用释放、字体对象、格式分发、词法/路径与包视图回调已调整；复核职责后98个编译对象的1019条符号引用中逆向引用为0。检查器和空例外清单已加入Linux CI。详见 [ARCHITECTURE.md](ARCHITECTURE.md)。公开/内部头文件及静态子库拆分仍待完成；按最新优先级，先做这两项，再继续以下功能包。

## 5. 后续顺序与验收目标

1. 对上述未关闭渲染项建立最小复现及独立参考，优先处理显式组色空间、原始墨色保真；覆盖至少3个正例、2个反例，再关闭对应矩阵项。
2. **WP4a**：按PubSec、EFOpen、JBIG2、JPX分别冻结输入矩阵；认证项至少10个凭据/损坏/权限/取消场景，图像项至少3正例/2反例。分别交付，保留现有Standard R2–R6回归。
3. **WP6–WP16**：按 [开发路线](HANDOFF.md) 的量化出口推进；完整阅读SDK、OCR、redaction与手机运行尚未完成。

保留版本0.19.0，不按内部步骤增加版本。公开结构体、符号与所有权规则遵循 [SDK兼容说明](SDK_COMPATIBILITY.md)。包装sink必须完整转发回调；ToUnicode维持严格校验；色彩断言按独立转换更新，原容差不扩大。
