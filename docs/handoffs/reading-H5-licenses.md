# H5：阅读 preset 的依赖和许可证交付审计

执行 [共同约束](reading-extra-index.md#全部包共同约束)。从 B=`b529513b7e8e8992786f8c679c0ec6c92110b035`
新建独立分支 `handoff/reading-h5-licenses`。本包可立即开工。

## 目标与边界

核对 `reading-core` / `reading-library` 实际启用和安装的第三方依赖、许可证与 notices，
给发布者一份可复现清单。只新增 `tools/check_reading_licenses.py`、
`tests/check_reading_licenses.py`、`.github/workflows/reading-licenses.yml`、
`docs/READING-LICENSES.md` 和本包证据目录。先复用现有工具；不改 LICENSE、依赖版本、
构建 preset、顶层 CMake 或仓库 About。

## 工作步骤

1. 阅读 preset、第三方 CMake、现有 license/notice 安装规则与已安装组件清单。
   对每项登记来源、固定版本/提交、启用条件、许可证原文路径和散列、随包是否安装。
2. 区分源码许可证、实际链接组件与可选功能；确认这两个 preset 禁用音频，
   不把 FAAD2/AAC 的可选构建结论套用到全部产物。
3. 云端干净构建并安装两个 preset，检查实际 stage 与依赖配置。
   缺许可证或来源不清逐项失败/待处理，不生成“全项目合规”结论。
4. 用最小正反例证明缺文件、空文件、错误路径或清单缺项会被拒绝；不引入扫描服务。
5. 若实际安装规则漏文件，报告具体修复建议与路径，交主代理修改共享安装规则；
   本包不以手工复制文件来掩盖默认安装缺陷。

## 出口

同源云端的两份 profile 清单、验证结果、原始许可证来源、未解决项与工件身份。
报告中明确区分“材料齐备检查”与法律判断；不重写历史版本许可说明。
只推本包分支，不合并、不发布版本。
