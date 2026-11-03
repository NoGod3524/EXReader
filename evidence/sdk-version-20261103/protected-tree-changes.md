# 受保护树变更清单

对比基线 95100501：

| 保护路径 | V 改动 |
|---|---|
| include | base.h 引用生成版本头；新增生成的 version.h |
| cmake | SDK 真源、版本头/pkg-config 模板、生成 include 导出、安装 SDK 版本读取 |
| CMakeLists.txt | project 读取真源，生成/安装版本头与 pkg-config |

保护集合其余 src、tests/fixtures、native.yml、reliability.yml、bindings 未改。共三项。

组件版本未改。R 必须取 V 之后提交重新登记 candidate/protected_trees 与新证据；本包不实施 refreeze。
