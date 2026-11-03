# V · SDK 版本身份单一真源 · 2026-11-03

分支：codex/sdk-version-single-source-20261103，基线 95100501eeef9c6325be8b3882aa400c99cf000f。

## 版本来源与消费者

唯一手写 SDK 版本：cmake/versions.cmake 的 EXR_SDK_VERSION=3.42.0；ABI epoch=1。core/pdf/pdf_edit/audio/library/textindex 组件版本与基线逐项相同，独立于总版本。

- project() 在 include 之后使用 EXR_SDK_VERSION；CMake package 使用 PROJECT_VERSION。
- configure_file 生成 build include/exr/version.h；安装随包发出；源树保留由 --sync-generated 生成并逐字节校验的副本，供直接头文件消费者使用。
- base.h 的 EXR_VERSION 引用生成的 EXR_SDK_VERSION；C/C++ 与 Swift/JNI runtime 共用该 C API。
- pkg-config 的 exreader.pc 使用 PROJECT_VERSION；README 版本行由 --sync-generated 同步，再由校验器校验。
- 宿主当前默认读取真源版本，模块通过实际安装头/包解析提供者；显式请求必须精确匹配，旧安装包保留从旧 base.h 读取的路径，不把旧 SDK 字面量改成当前值。
- 历史“未来版本”拒绝测试的 future 值从真源计算；仍固定重放旧 SDK 的迁移矩阵保留旧身份。

## 逐项登记规则

完整扫描位置与旧值在 scan-before.json；这是变更前记录，不是所有旧值均需替换的清单。当前校验覆盖 root CMake/README/生成头、workflow 的 EXR_HOST_SDK_VERSION/EXR_SDK_VERSION 以及 tests 下的版本字面量。

版本例外登记在 tools/version_literal_exceptions.json：每项精确匹配 file:line + literal + purpose，另绑定该行 SHA-256；无目录或文件级跳过。当前计数：{"frozen_baseline": 531, "negative_case": 50, "migration_compat": 7}。

- frozen_baseline：冻结 SDK commit/header 原始字节 SHA-256，加冻结测试 fixture 的 commit/原始文件 SHA-256/原始行；CI 核对 Git 对象原字节与当前登记行。
- migration_compat：明确的测试 runner 调用及仍存在的 workflow 引用、各自行号/行与文件散列、移除条件。
- negative_case：配套 guard 拒绝断言的文件/行号/范围/散列，并验证 returncode!=0、Java false/accepts 断言或 mutation 的拒绝分支；没有该断言不能登记。

文件/行/literal 消失或改变、冻结对象散列不符、迁移引用/移除条件缺失、拒绝断言失效、重复条目均报错。retired-exceptions.json 记录 V 中已从原字面量改为源版本注入并移除的条目；CI 不自动忽略失效条目。

## 本地验收（Actions 结果另记）

| 验收 | 本地结果 | 证据 |
|---|---|---|
| 干净内容一致性 | PASS，SDK 3.42.0 / ABI 1 | positive.txt |
| 人为改 project 旧值 | 校验器 exit 1；CMakeLists.txt:3；expected 3.42.0 | negative.txt |
| 安装包三渠道与真实链接 runtime | CMake / generated header / pkg-config / runtime 均为 3.42.0，ABI 1 | installed-channels.json |
| README 等于真源 | PASS，版本行由同步脚本生成并校验 | positive.txt |
| 证据与保护集 | 本目录保存；三项保护路径变化 | protected-tree-changes.md |

额外正反例验证：有效登记通过；失效行、改 literal、错冻结字节、迁移引用损坏、缺移除条件、负例断言损坏、重复条目七种均拒绝。安装包验证使用 Windows MinGW Release、现有离线依赖源码与裁剪核心构建，不授予 R3 性能或完整产品验收。

复核命令（均在仓库根目录）：

```bash
python tools/check_version_consistency.py
python tools/check_version_consistency.py --self-test
python tests/check_version_consistency.py
# 已有安装包与独立可写 build 目录：
python tests/check_sdk_install_version.py --sdk "$SDK_PREFIX" --build-dir "$PROBE_BUILD"
# 真源更新后只同步派生副本：
python tools/check_version_consistency.py --sync-generated
```

CI：sdk-version-consistency.yml 仅 pull_request / workflow_dispatch；identity 检查有效内容与登记义务，reject-version-drift 作业注入错误并断言子进程返回 1，精确输出位置与期望值。云端正例 run 41707789559（source 8cfb2174cfc6e25e3227aa4418448e63f0bd383f）两作业 success；真实红色负例 run 41707978252（source 59385f74edfd69e68f3586e9d22fb3e826da7e9c，仅改错 project 一行）两作业 failure，实际日志包含 CMakeLists.txt:3 与 expected 3.42.0。见 cloud-verification.json、ci-positive.txt、ci-negative.txt。临时负例不进入 V 的产品提交。

## R 的前置关系

本包改变 protected 集合中的 include、cmake、CMakeLists.txt 三项，native.yml 未改。**R 的候选必须基于 V 之后的提交，不能沿用 95100501 的散列。** 本包未 refreeze、不更新 SDK 基线登记/性能预算，不执行 C/R，不改 catalog、Settings、默认分支或其它会话分支。

本地安装包三渠道已实测；完整 native 矩阵 run 41707789690 尚未结束，不据 SDK 专项 CI 授予整个 native 矩阵通过。

后续 native 观测：apple-mobile job 126167587852 已越过 SDK 版本比较，当前失败是缺少 `stage/iphonesimulator/include/exreader-product`，非 SDK 版本不符。原 run/job 链接与失败步骤见 native-observation.json；本包未扩展为产品依赖修复。
