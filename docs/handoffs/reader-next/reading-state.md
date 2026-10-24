# Handoff：真实SDK阅读状态与跨设备记录联验

先读[共同约束](README.md)。从固定起点新建 `codex/reader-reading-state`。

## 要交付的能力

用冻结SDK真实捕获的阅读位置／书签／标注，验证产品修订可表达并在另一独立书库安全恢复。
已有wire校验、projection与网络测试不替代本包的真实SDK闭环。

先拥有新增 `apps/reader/reading-state/**`、`tests/reader_reading_state/**`、
`.github/workflows/reader-reading-state.yml`、`docs/READER-READING-STATE.md`及本包JSON。
可仅读取现有commands/revisions/sync。共享头／源码、旧wire规则或版本需要变化时，
先交完整兼容性证据和最小版本化方案，由root协调，禁止偷偷放宽v1条件。

## 首先解决契约兼容性

实际检查 `exr_anchor_create`、EPUB章内及固定页公开API，不用合成JSON代替捕获。
已发现需明确验证的差异：SDK点锚点允许 `start==end`、`exact`为空，
而当前wire v1的selector要求非空exact；无文本固定页亦须检查。
不可发明引文、修改UTF-8偏移、用页码猜测重排位置，或把未找到当FOUND。

给出每个真实案例的SDK输出语义、原wire验证结果和接收端公开resolve结果。
若需要扩展，必须明确版本、旧记录的精确字节保留和旧客户端拒绝行为，
保留现有v1正反例；先完成这个决策，再实现可消费的适配层。

## 实际闭环

- 两个独立SDK书库和两个schema1产品库，同一本原书在两端使用不同SDK本机ID。
- 普通重排UTF-8位置、EPUB part_path、PDF/CBZ page_id与固定页模式。
- 开头／结尾／多字节边界、空引文点、重复文本、歧义／未找到、无文本固定页。
- 进度、书签和标注增改删的稳定全局身份、并发头、墓碑、精确重试和离线历史。
- 只在公开resolve返回FOUND后调用公开SDK持久化／导航；歧义和缺失保留原记录。
- 接收远端状态不强制跳转正在阅读的页面。SDK库与产品库不是一个跨库事务，故障分别恢复。

先用installed C/C++消费者证明上述闭环；UI由root及各平台接入者消费固定接口。
书签需要明确产品表示；不得自行增加SQL表或未知wire实体类型。
原书、选择器、fixture与所有执行只在Actions生成／运行。

## 验收

交可复验完整SHA、同源双端原件／记录散列、真实SDK捕获与resolve状态、
安装消费、零误定位断言、保留失败和逐项未覆盖面。
SDK八条冻结路径不变，不直接读写SDK私有表，不以系统SQLite冒充原生provider。
没有SDK实际往返证据时只登记协议兼容性研究，不能授予阅读状态同步完成。
