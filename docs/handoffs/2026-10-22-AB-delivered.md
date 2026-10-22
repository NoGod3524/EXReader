# A/B 固定交付与 C 接续事项

后续结果：C 已完成全部接续并获联合验收，见 [最终登记](2026-10-22-ABC-accepted.md)。下文保留当时输入与迁移要求。

2026-10-22。已用 GitHub 连接核对运行、全量 jobs/artifacts、完成日志与仓库证据；未下载工件或执行本地测试。
R1–R6 继续暂不启动，当前只收口 A/B/C。

## A：Android 声明范围通过

- 受测源码：`8a6636ed8ac6db06ab84e174f5a01c49d12511dc`。
- 交付 HEAD：`31b36f305085cb8b1468b1d9b9b1ea2d67ee1656`；按原历史合入。
- run [39831715741](https://github.com/NoGod3524/EXReader/actions/runs/39831715741)，attempt 1，唯一 `android-host` job `120009269825` 成功。
- 完成日志：原 45/45、独立 10/10，均零失败零跳过；48/48 门禁正反例通过，最终 `accepted=true`、`problems=[]`。
- 唯一工件 `12449232819`，`EXReader-WP13-Android`，149127088 字节，未过期，源码与 run 相同；
  digest `sha256:1c5ee0f59fb8f30227ca8985eefb0d320cdc02dee6a9e1733ef6fa18bc825e1a`。
- 云端只读诊断 run `39833457474` 完成日志重新核对固定工件，两套逐项记录全 pass；
  49 页、49 native next、0 recovery，序列耗时 63603 ms。诊断不替代原验收。
- 范围仍为 API34 x86_64 模拟器；真机、签名、TalkBack 和其他格式出口另列。

注意交付身份：受测源码到交付 HEAD 的 GitHub compare 显示两处路径：
`docs/WP13-ANDROID-REVIEW.md` 以及 `.github/workflows/wp13-android-diagnostics.yml`，
不应统称“只有文档差异”。C 要保留诊断工作流变更并将全部非 OPDS 路径纳入 H 之前的冻结。
原通过仍只绑定上述受测源码。

## B：独立表单文件出口通过

- 受测源码：`a326fd38bbbb481da74657d682f649b1f45f7e2c`。
- 交付 HEAD：`97e33452a96f1c042dcc98510b51f3e4af7253ef`；直接合入，不 rebase 受测历史。
- run [39833769030](https://github.com/NoGod3524/EXReader/actions/runs/39833769030)：
  `corpus`、Linux、Windows、sanitizer、`evidence` 五个作业均成功、同源。
- 四份工件 `12449542654`、`12450390978`、`12449303685`、`12450445588` 均同源、非空、未过期且有有效 SHA-256 digest。
- 仓库 [语料汇总](https://github.com/NoGod3524/EXReader/blob/97e33452a96f1c042dcc98510b51f3e4af7253ef/docs/validation/wp9-acroform-corpus/summary.md)：
  三个执行平台各 75/75 文件、零失败零跳过；Linux 2032 断言，Windows/sanitizer 各 1966，harness 各 1798。
  evidence 作业严格汇总 `problems=[]`。
- 75 份为原创生成的独立结构语料，包含 35 正例、29 写拒绝、3 取消、8 不可读树；
  不代表 75 份真实出版物或全部成功编辑。
- 安装消费 Linux/Windows 各覆盖 31、跳过 2 个非 ASCII 值、失败 0；不能将此项登记为零跳过。
- 至少 30 份独立文件出口已满足；未覆盖的高级表单、权限、加密写回、bidi 外观等继续列在组件支持范围。

## C 接续前必须更新

1. A/B 固定输入已到齐，阶段三/四可以接续；核对各工作树当前状态，合入交付 HEAD 并保留失败历史。
2. B 相对原交付虽无 `src/`、`include/` 变更，但修改了受保护的顶层 `CMakeLists.txt`。
   原 K 的八条受保护树因此不能直接沿用；合入后重新云端验证 SDK、安装/裁剪/消费者与 sanitizer，冻结新 K。
3. B 的 `acroform.yml` 从 3 作业变为 5 作业。旧联合检查器仍按 3 作业校验，必须更新期望、正反例、
   语料/参考/消费者证据覆盖与最终工作流契约；保留原十组及 spacing，目标成为 **12 组、35 个上游作业**。
   12 个 run ID 的数量不变，联合门禁自身作业另计；新计数尚未在集成分支实现或授予通过。
4. Android `SDK_BASE` 与 OPDS `BASELINE` 指向新 K；Android pending 守卫转为有效契约，所有权祖先合法登记。
5. 全部非 OPDS 修改（含门禁与证据工具）结束后冻结 H，最后合入 OPDS 并登记 `HANDOFF=H`，冻结 S。
6. 全部生产者在 S 重跑，逐项证据及严格汇总通过后才授予联合验收。若合入后实际作业结构再变，
   先更新并验证契约，不能丢弃新增作业、引用旧源结果或只改计数跳过行为校验。

本轮只更新文档分支的交付登记与 C handoff，没有执行合并、更新集成脚本或派发工作流。
