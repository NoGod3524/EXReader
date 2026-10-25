# 模块的显式 SDK 候选选择

独立分支 `codex/reader-sdk-version-support`，默认仍3.40.0。四个共享模块reading-state/search/navigation/batch-import和desktop构建器新增显式 `EXR_SDK_VERSION=3.41.0` 选择；只允许3.40.0与已授权新候选3.41.0。安装Config固化所选EXACT版本，消费者不能静默降到另一SDK。模块公共头、实现、旧消费者和产品schema不改。

`build_linux_host.py --sdk-version` 默认3.40.0，可显式3.41.0；打包时核实际宿主 `--version` 和ABI1。当前本分支不修改宿主接线；该选项的实际打包由GTK独立候选继续验证。

Actions分别重建冻结9854061的3.40及已基础验证b911815e的3.41，独立安装各自模块；运行原阅读状态、搜索、目录和批量导入消费者与故障回归，并核每个安装Config的具体依赖版本。再把3.41包交给真实3.40前缀，要求配置拒绝；3.42选择也必须拒绝。

受测源码 `f680aeaddfb1ecc67ead353554f5b91a5703f72f` / [run40166479919](https://github.com/NoGod3524/EXReader/actions/runs/40166479919) attempt1 已success。Linux作业 `121088467261` 在两个SDK前缀下均运行原121项旧客户端及18个真实v2捕获、搜索/目录消费者、批量导入668项及故障回归；四份安装Config各自记录所选EXACT版本。真实混装与不支持3.42的配置均被拒绝。工件 `12587803903`，63253107字节，SHA-256 `02affa7dcae5d6085f066e0ea375ca2e65c2998c199fe7f3eef393cda20af36b`，有效期至 `2027-01-23T05:42:04Z`；源码/轮次/每份原报告和Config的散列由该轮result.json记录。本地未执行构建、语法或测试。

授予范围为Linux上这两个具体SDK源码与四个模块的安装选择。GTK真实打包另验；其他平台、整产品或六平台SDK迁移未授予。旧3.40记录使用的parser身份与3.41不同，本轮两个版本各自新建记录不证明跨版本旧库迁移。

首轮source `27b80c35` / run `40166114935` 保留失败：root把旧121项探针接到了已支持v2的新修订客户端，十项“旧客户端必须拒绝v2”正确拒绝本轮。改为复用共同宿主的固定210403d旧客户端和独立旧adapter，再由原v2 checker同时验证原121及十八个真实v2捕获；不修改任何旧断言。GTK inspector与固定页UI另加显式版本选择，默认3.40保持，固定页原24项不删。
