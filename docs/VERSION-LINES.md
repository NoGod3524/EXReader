# SDK version lines

F06 交付记录中的 3.42 产物 ← `8357eafa28423a7ab93ba08b823af80f01ad1505`。交接时记为“本仓库不可取得，存在性未核实”；2026-11-03 本次复核已可通过本地 Git 与 GitHub commits API 取得该提交，源码头与 CMake project 均标为 3.42.0。取得提交本身不等于重新核实 F06 产物与该源码的对应关系。

本次 V 之后源码亦为 3.42.0 ← `21add50a29e6b1371ca6e213f0ee3c0907734b68`（本次复核的 V 快照；含 CMakeLists.txt、cmake/*、include/exr/base.h、include/exr/version.h 的受保护树变更）。

两者同号不同源；refreeze 完成后统一升 3.43.0 消除歧义。当前不改版本，ABI epoch 保持 1，组件版本保持独立。

合并顺序为 V → P → C，均进入 ledger/base-20261103。R 的候选 C 必须取 P 落地后的提交，包含 V 的受保护树变更和 F07 provider 变更，不能使用 21add50a 或 95100501。后续 3.43.0 的版本变更也须纳入其实际候选和证据登记，不能沿用先前树的证据。
