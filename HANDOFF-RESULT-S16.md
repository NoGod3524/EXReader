# HANDOFF-RESULT-S16 - 跳转历史的 raw3 显式兼容

交回方:DeepSeek(S16)。本节只陈述本包真实做过的源码、Actions 记录与工件身份。
未跑过的项目一律标为未验证,不用文档或设计代替证据。

## 1. 范围、所有权与起点

- 分支:`codex/reader-next-s16`(远端 origin,仅该功能分支,无 PR/tag/Release)。
- 固定起点:`e67d87cbeabb2457e0852f681ef0b27b2c0da4d8`(CI 用 `git merge-base --is-ancestor` 校验)。
- 独占写入(实际仅改动这些路径):
  - `apps/reader/jump-history/`
  - `tests/reader_next_s16/`
  - `.github/workflows/reader-next-s16.yml`
  - `docs/reader-next-s16/`
  - `HANDOFF-RESULT-S16.md`
- 未改:`apps/reader/reading-state`、`apps/reader/revisions`、`apps/reader/store`、
  `apps/reader/sync`、`apps/reader/commands`、`apps/reader/reading-commands`、
  `apps/reader/annotation-view`、SDK 源码树、产品 schema、原测试与原裁判。
- 依赖来源(CI 断言,不是声明):SDK 源码树与批准候选
  `edddc463c06ed5731195cdb8f06b2df6dff7699e` 逐字节相同
  (`git diff --exit-code edddc463 HEAD -- src include cmake CMakeLists.txt tests/fixtures bindings …`);
  冻结旧 SDK `9854061be331fe603a1822d9b2b36ee357154927` 仍可解析;产品 schema
  `f32bb8aa18ed3de286900f19ce4230fd93435dd0` 的 `apps/reader/store/001_catalog.sql` 未变。

## 2. 受测源码与文档 SHA

最终受测 source(全部构建/测试/工件解析所绑定):`1f588ca880e8dde7c8293a2769e3663194194acd`。

| 文件 | blob SHA(`git rev-parse 1f588ca8:<path>`) |
| --- | --- |
| apps/reader/jump-history/CMakeLists.txt | 1ca62ba268128a153ed971e0c638bfbadd698826 |
| apps/reader/jump-history/EXReaderJumpHistoryConfig.cmake.in | 48368ebaddb6df97d65d27921160685f782252c8 |
| apps/reader/jump-history/include/reader_jump_history.h | fe0d163ab3af863cb5cbf6b11fa2ca43d905d6fb |
| apps/reader/jump-history/src/jump_history.cpp | ce0bf879804aaa2e4c4c46ab577dbee17a80321b |
| tests/reader_next_s16/run.py | bfb804e0649b828c63d8b516e64f3fa3e2491287 |
| tests/reader_next_s16/check_raw.py | 37847830df4ee839a87df90592cfbe52fe6f7231 |
| tests/reader_next_s16/check_artifacts.py | 15600be23f3d92885c5ed00d1dda0d0329756860 |
| tests/reader_next_s16/consumer/CMakeLists.txt | 489da0e0b6bb70a3ca532a58c5b36fb3158cb93a |
| tests/reader_next_s16/consumer/api.c | de2e1c11ee8c83f460e5a75121df4963c9a8b5ae |
| tests/reader_next_s16/consumer/probe.cpp | 696cc0d29d13a1a647b9e21165a9fcda9ab8a996 |
| .github/workflows/reader-next-s16.yml | 9bfc028e2f4137496306157a1e2a56af292d53ab |
| docs/reader-next-s16/README.md | 0042726184603aa860c5d35176b8abe47fb140fb |

本文档自身是“文档封存”提交(提交信息带 [skip ci]),不改变上文受测 source。

## 3. 改动内容(最小面)

模块只新增一个默认关闭的候选配置:

- `option(EXR_READER_SELECTOR_BYTES_CANDIDATE "…never default" OFF)`;
  默认安装 `EXReaderJumpHistory 0.1.0`(依赖 `EXReaderReadingState 0.1.0`、
  `EXReaderRevisions 0.3.0`),候选安装 `EXReaderJumpHistory 0.2.0`(依赖 0.2.0 / 0.4.0),
  两族版本号与包配置显式区分。
- 头文件新增 `READER_JH_INSTALL_VERSION`(`"0.1.0"`/`"0.2.0"`);
  `READER_JH_VERSION` 与 `READER_JH_STRUCT_VERSION` 在两族都不变,
  所有原消费者断言与结构布局保持。
- 候选族新增两个显式入口:`reader_jh_commit_fixed_v3`(用 `reader_rs_encode_fixed_v3`
  编码 `fixed_page` 锚 v3)、`reader_jh_commit_wire_raw_v3`(存放 raw 校验器接受的 wire,
  含原样复用的 v1/v2 wire)。两者沿用原有 UNCHANGED/COALESCE/截断/淘汰/记账/原子失败/线程规则。
- 身份语义:锚 v3 的 `exact/prefix/suffix` 是字节。位置键仅对 v3 追加“存在位 + 字节长度”,
  因此内嵌 NUL 不会截断选择器,NULL 上下文与“已分配空串”不是同一地点;v1/v2 的键逐字节不变。
- 旧入口在本安装内仍保持旧行为:`reader_jh_commit` 仍走 `reader_rs_encode_v2`,
  `reader_jh_commit_wire` 仍走 `reader_rs_decode`,因此旧入口拒绝锚 v3 wire 与 raw store,
  新入口拒绝 legacy store;运行期两族不混用。
- 不写 schema、不写 wire、不新增数据库、不引入第二解析器;未改 reading-state/revisions/宿主。

族隔离共四道(CI 全部实测):

1. `find_package(EXReaderReadingState … EXACT)` 版本互斥;
2. 构建期检查精确导入适配器目标必须带/不带 `EXR_READER_SELECTOR_BYTES_CANDIDATE=1`
   (伪造版本文件也拦得住);
3. 安装包版本号互斥;
4. 包配置里的 `_exr_raw_guard_target` 复核来源与能力。

## 4. 最终受测运行(同 source / run / attempt / jobs)

- source:`1f588ca880e8dde7c8293a2769e3663194194acd`
- run:`40229935121`,attempt:`1`
- workflow:`.github/workflows/reader-next-s16.yml`
- jobs(均 completed/success,同 head_sha 同 attempt):
  - `S16 consumers (Linux)` id `121279276994`
  - `S16 consumers (Windows)` id `121279276596`
  - `strict S16 evidence` id `121280188346`
- 汇总判定:`jump_history_raw_candidate_accepted=true`、`problems=[]`、
  `host_wiring_accepted=false`、`gui_accepted=false`、`adopted=false`。

### 4.1 各平台结果(两平台一致)

| 项 | 数值 |
| --- | --- |
| 原套(固定起点 baseline 安装) | checks_total=149、checks_failed=0、accepted |
| 原套(默认 0.1.0 安装) | checks_total=149、checks_failed=0、accepted |
| 原套(raw 0.2.0 安装) | checks_total=149、checks_failed=0、accepted |
| 默认安装复现 baseline | default_equals_baseline=true(cases/lifecycle/checks/no_write/books 全等) |
| 新 raw 套件 | checks_total=162、checks_failed=0、cases_total=6、moves=3、accepted |
| 默认安装 C 消费者 | checks_total=21、checks_failed=0、accepted |
| 证据协议自测 | protocol_negative_cases=37、accepted |
| 头文件 | 默认安装头 = baseline 头 + 纯插入(difflib 还原校验);两族同一份带守卫的头 |
| 默认归档 | 不含 reader_jh_commit_fixed_v3 / reader_jh_commit_wire_raw_v3 / reader_rs_decode_raw_v3 |
| raw 归档 | 三个符号均在 |
| 导出目标 | 默认族不带、raw 族带 EXR_READER_SELECTOR_BYTES_CANDIDATE=1 |

版本(两平台一致):jump_history=0.1.0(ABI/wire)、install=0.2.0(raw 族)、
reading_state=0.2.0、revisions=0.4.0、sdk=3.41.0。

### 4.2 4 个混配安装负例(均被拒,记录在 result.json)

1. `negative-raw-against-default`:raw jump-history 配 0.1.0 适配器 → requested version "0.2.0" 拒绝。
2. `negative-default-against-raw`:默认 jump-history 配 0.2.0 适配器 → requested version "0.1.0" 拒绝。
3. `negative-original-consumer-against-raw`:原消费者向 raw 安装请求 0.1.0 → 拒绝。
4. `negative-faked-family-target`:复制默认安装、只把适配器版本文件改写成 0.2.0(档案/头文件齐全),
   构建期能力检查以 `Raw candidate jump history requires the raw candidate reading-state target` 拒绝。

### 4.3 程序 hash(证据作业在 Actions 内重算并与 summary 比对)

- Linux:
  - s16-raw-probe sha256 `62ff29ae8db23424cc8a3028cee01144a3d55325dd99f63aa69f46f77e086fc0`(9668400 bytes)
  - s16-c-consumer `0b1fe648df6fd7481a7d764d590a5f2edd204302a970630f58c28994ded3b1ae`
  - 默认 C 消费者 `40fa51be27fcec20258de94f31fc2978e2696beaf827cd13805fbaca30d95795`
  - 原套 probe `dd5f7eff2e8eb3b280aff6e047637bfdb144a1204513ec6aa37bc79968dec36b`
  - 原套 C 消费者 `7a22dd55ed7691d9339799a9db2beffc236591055dbd92583721129df664ac2a`
- Windows:
  - s16-raw-probe sha256 `96024aa60e74175a821b15a432372b40252846b20d2252b82ac21927191f00da`(7074304 bytes)
  - s16-c-consumer `22ecf39b18f229ecfa1a23b14d7fc4fc287c02593b15560756a03f79de5196f1`
  - 默认 C 消费者 `355f6148b99c18b9f448aae93d1abc6a8d398d78e4f32e3db5e927c5f71add6a`
  - 原套 probe `f406d4d8abe16ca71935076c72e6a8bd29085c3df7a0c3f3f39fa163877cb64e`
  - 原套 C 消费者 `16ee5150097aff15da1b8654661a7b262c2deeae1ca1e0a682bb62bf7b8cca2a`

### 4.4 原工件身份(唯一 ZIP,size / digest / expiry;证据作业在 Actions 内下载后复算)

| 平台 | 工件名 | artifact id | bytes | SHA-256 | 过期 |
| --- | --- | --- | --- | --- | --- |
| Linux | reader-next-s16-Linux-40229935121-1 | 12611804291 | 12048889 | 76f22b123719f01bba7ec5dba9fdfb5733c1ec47b133a9049a00f5e6d49ec35d | 2027-01-23T20:15:49Z |
| Windows | reader-next-s16-Windows-40229935121-1 | 12611749406 | 9901869 | 7568f9abea2196a0e5f968dfc680b33b8f0bbb233aabe4303732ad4c4a83185c | 2027-01-23T20:15:49Z |
| 证据记录 | reader-next-s16-evidence-40229935121-1 | 12612143694 | 3401 | 547f5f48cf8ece3d1f00f25a7aeb351a3389b080a39a9ae78e3621afa4c2a9c4 | 2027-01-23T20:15:49Z |

api_bytes == zip_bytes 且 api_digest == zip_digest 已由证据作业逐平台判定;工件未过期。

### 4.5 证据作业在 Actions 内实际做的认证

下载两个同 run/attempt ZIP → 复算 size/SHA-256 → 绑定 summary 的 source/run/attempt →
复核 report_sha256 与“上传的 probe 二进制就是 summary 记录的那个程序” →
校验 162 个唯一具名检查全为字面 true、probe_checks_total 一致 →
校验 no-write 8 项与 7 个 raw 语义标志、5 个版本值 →
校验默认安装消费者、原套 raw/baseline 两份摘要、result.json 的
accepted / default_equals_baseline / header_pure_insertions / default_install_has_no_raw_symbol /
4 个负例 / host_wiring / gui / adopted →
跨平台比较 originals、6 个 case 投影、lifecycle、versions、no-write 与语义标志。
全部通过,problems=[]。

## 5. 保留的失败(不删除、不降级)

按时间顺序,全部是本包自己的缺陷,均已定位并修复;模块语义与 wire 从未在失败中被放宽:

1. `40227717405`(source 260fcfa3):开跑前我主动 `gh run cancel` —— 证据协议自测把身份绑到了
   合成值(`setdefault` 不覆盖真实 GITHUB_SHA),必然失败。未计入“完整 CI”。
2. `40227819225`(source 3a28d024):Windows 的 vcvars 步骤用单引号,环境变量不展开;
   同轮 Linux 因我把“默认安装头里不应出现 raw 声明文字”当成断言而失败
   (实际两族共用一份带 #ifdef 守卫的头;正确判据是导出目标的能力定义与归档符号)。
3. `40228161056`(source 2430dc7b):raw 族的原套消费者副本只算了补丁文本却没写回文件,
   于是仍请求 0.1.0 而配置失败。
4. `40228583416`(source d8c5c5b6):三套原套全绿;raw 套件 159/162,3 项失败全是新测试缺陷
   (EPUB 路径用 char* 指针比较 ×2;锚 v3 的 fixed_page/3 路由从未被记录)。
5. `40229084653`(source 66026193):raw 套件 162/162、默认消费者 21/21、前 3 个负例通过;
   第 4 个负例的伪版本前缀缺归档,CMake 在 include 导入目标时就报“文件不存在”,没走到能力检查。
6. `40229448166`(source 01c6d6cd):两个消费者作业全绿;证据作业唯一失败项是
   default_equals_baseline 被写在 original_suite 子对象里,根部为 null。

**轮次预算**:共同约束是“每包最多三轮完整 CI……超过三轮如实交回”。本包实际用了
**6 轮完整 CI + 1 次主动取消**。超出原因全部是上述“我自己测试/CI 脚本的机械缺陷”,
模块与 wire 语义没有在超轮过程中被改动或放宽;此处如实记录,不作“三轮内完成”的表述。

## 6. 未验证项与不授予项

- 宿主接线:四个生产宿主(Windows/GTK/Android/Apple)未接入;GUI、菜单、快捷键、对话框一律未做,
  host_wiring_accepted=false、gui_accepted=false。
- 持久化/跨设备/同步实体:跳转历史仍是内存结构,未验证重启、跨设备或新同步实体。
- 真实用户书库、私有云与真实账号:未使用;TLS 校验未关闭;凭据只用 runner 生成的测试秘密。
- macOS 未在矩阵内(本包只要求 Windows/Linux 双配置)。
- 性能:只验证了文档化的条目/字节上限,没有延迟或 CPU 预算结论。
- raw 候选**未被接纳**:它不是批准的 SDK,也不是产品默认;adopted=false。新 SDK patch 类产物一律
  标为“未接纳候选”,即使版本字符串未改。
- 最终同源验证与真正接纳由 root 负责;本交回不代替 root 的共同源码六端验收。

## 7. 复现命令(全部在 Actions)

- 触发:推送到 `codex/reader-next-s16`(或 workflow_dispatch)。
- 单步:`python3 tests/reader_next_s16/run.py`(要求 GITHUB_ACTIONS=true,HEAD==GITHUB_SHA)。
- 判读:`python3 tests/reader_next_s16/check_raw.py --mode raw|default …`;
  汇总:`python3 tests/reader_next_s16/check_artifacts.py build/reader-next-s16-evidence`。
- 本地只做源码/文档/Git;未在本机编译、跑测试、生成夹具或解析工件。

## 8. 结论

模块层面的 S16 目标(默认关闭的 raw 候选、显式 raw 入口、NULL/NUL 身份、v1/v2/3 与四路由复现、
真实公开 SDK capture/FOUND/重开、混配拒绝、边界/取消/线程规则、无写入证明)在同源
Windows + Linux 双平台、三族原套 + 新 raw 套件 + 4 个负例 + 严格工件认证下全部通过。
交付仍是**仅模块**:不含宿主接线、GUI 与性能承诺,raw 候选仍是未接纳候选。
