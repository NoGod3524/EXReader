# 原生宿主与 WebDAV 验证记录

| 验证 | 受测源码 | 原始运行与结论 |
| --- | --- | --- |
| iPhone 标注独立验证 | `94fb236a4a2da87dfbaf4f1dd2a47885d615a230` | [41170540560](https://github.com/NoGod3524/EXReader/actions/runs/41170540560) 失败，工件 `13031773957`。台账记录包含原始归档哈希及 Wave 3 用例范围。 |
| F02 原件传输、F04 六端同步 | `ec11cf862ca3b44483d7e8c4726ae748ab438337` | [41306566948](https://github.com/NoGod3524/EXReader/actions/runs/41306566948) 第一次运行成功，15 个作业成功。 |
| F08 硬件性能采样 | `1c4eac3e` | [41395573011](https://github.com/NoGod3524/EXReader/actions/runs/41395573011) 14 个对照通过。Android 采样退出码为 1，性能验收仍待完成。 |
| F09 六工件诊断 | `055d196789b26ecfe466cb14c7ada857fb9069d3` | [41379062673](https://github.com/NoGod3524/EXReader/actions/runs/41379062673) 第一次运行的诊断作业成功，验证范围为六个归档的 315 个成员，完整 F09 验收仍待完成。 |
| F10 组件验证 | `4db961144b00c9004e2775b9e1e57e6ea7a31cb7` | 82 个用例、880 项断言、38 项负向测试。完整 F10 另需同源消费者、原生宿主及凭据验证。 |
