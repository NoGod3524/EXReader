# R candidate protected-tree changes

| 工作包 | 受保护项 |
|---|---|
| V (#29) | include、cmake、CMakeLists.txt |
| P (#30) | CMakeLists.txt、.github/workflows/native.yml |

去重后四项：**include、cmake、CMakeLists.txt、.github/workflows/native.yml**。CMakeLists.txt 在 P 中只增加 windows_accessibility.inc 的 install 条目，保留已有 install、目标及版本字段。

R 候选必须取 #30 合并之后 ledger/base-20261103 的提交，并包含 provider 最终变更；不得使用 0dba1b85 或此前提交，也不得把旧候选的证据授予新树。本步不 refreeze、不跑完整矩阵。

Windows 打包正例必须来自实际安装后的 SDK 和实际生成的 exe。缺失 staged include 的负例记录实际退出码与 EXPECTED 完整路径；另验证缺 exe 会在创建输出目录前失败。
