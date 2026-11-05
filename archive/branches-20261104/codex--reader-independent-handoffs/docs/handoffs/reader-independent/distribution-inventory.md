# G09：产品依赖、许可证与离线分发清单

先读[共同约束](README.md)，接受其中全部不变项与云端执行限制。
固定实现起点：`f43baf9182d75907c0cb5d6f77048f27bca8c950`。新建独立工作树和分支 `codex/reader-distribution-inventory`。
类型：发布准备；优先级：P1；分发：DeepSeek Harness。

## 文件归属

- `tests/reader_distribution_inventory/**`
- `.github/workflows/reader-distribution-inventory.yml`
- `docs/READER-DISTRIBUTION-INVENTORY.md`
- `docs/validation/reader-distribution-inventory.json`

除此之外的目录只读。不要修改共享构建、已有工作流或本交接目录。

## 实现与边界

对固定基线实际构建安装的SDK和应用可选模块做文件清单、版本、字节/SHA、真实动态/静态依赖、许可证原文和notice来源。复用既有许可记录，核对实际产物而非只抄CMake开关。
生成机器可读SBOM（标准SPDX或CycloneDX）和人可读分发材料；reading配置不应混入未启用的音频/GPL可选项、WebView、测试凭据或构建机绝对私有路径。
不改旧SDK发布流程/许可证声明，不创建tag/Release、不签名、不上传正式商店；有争议许可证列依据与未解项，由root收口。

## 云端出口

至少三桌面实际安装结果、实际依赖命令与清单逐字对应；测试漏文件/散列错/缺notice被拒绝。
报告区分生成材料成功与发布就绪；缺许可证或来源即不能授予就绪。记录未覆盖移动打包范围。
同一source/run/attempt逐项验收；参考通过记录不转移到本包源码。任何未覆盖能力继续保持未授予。

## 先读的实际代码

- `docs/READING-LICENSE-REVIEW.md`
- `docs/R6-READING-RELEASE.md`
- `tests/reader_credentials`

## 交回

推送功能分支；完整受测SHA、最终纯文档HEAD/差异、run/attempt/job、具名结果、工件ID/字节/digest/有效期、原失败及剩余工作。不要替root合入。

