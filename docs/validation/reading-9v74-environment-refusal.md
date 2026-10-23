# AMD EPYC 9V74 环境拒绝

PR13 默认门禁 run `40035574150`、attempt 1 的 performance 作业 `120694075328`
拒绝测量。workflow head `4aa25cf7b1aef19b31a1a86830d59e8880c3b57a`，实际 merge
源码 `6d582273241ac014622fadda5c20111f97056840`。原因是严格环境注册表没有该 CPU。
保留该次失败，不将 GTK 专项通过授予默认门禁。

只读原件诊断源码 `e65aa6243274f318aa4ff3ab22d70e2b98cf220d`，run `40036994530`、
attempt 1、作业 `120698828475` 成功。它只在 Actions 读取并验证原工件：

- 工件 `12536408174`，17455734 字节，SHA-256
  `20a2f4013161c3b693c7fc4a6f657346a83880e99e94f47cc68daa953a4f6847`。
- 原 summary SHA-256 `46a42672290615450188471c4a96a8efc8d02ab8b5b4513ac22caf890c2ede74`。
- 环境为 Linux/X64/ubuntu22，CPU `AMD EPYC 9V74 80-Core Processor`，GCC 11.4.0、
  Poppler 22.02.0。与三个已登记环境逐字段比较，只有 `cpu_model` 不同。
- 原 summary `measurement_valid=false`、`accepted=false`，原生/参考样本数组为空。
  诊断 `diagnostic_completed=true`、`measurement_performed=false`、`accepted=false`。

诊断工件 `12537735838`，1081 字节，SHA-256
`d69eb82e35260cf93ec05fce24b52a22e7bd9f109becf844bc127b4fe8796d93`，上传日志身份一致。
旧预算和注册表保持原字节。9V74 需要独立测量、原始证据核验、预算导出及后继严格
enforcing 才能授予；本记录不登记或推导任何新数值预算。

一次独立采样请求 run `40038000838`（源码 `d352d62b`）在构建前要求精确 9V74，
实际分配 9V45，预检按约拒绝；没有执行测量，也没有新基线。该次身份步骤尚未执行
使工件名为空，原始日志保留。后续将身份登记移到 CPU 预检之前，并将分配记录纳入
原件工件；不反复启动运行碰运气，不将 9V45 的时长拼成 9V74 基线。

身份顺序修复后的验证 run `40039952719`（源码
`d0af426a9b88000afe5bd05677d0cb8469bd7e49`）实际分配
`Intel(R) Xeon(R) Platinum 8370C CPU @ 2.80GHz`，精确 9V74 预检再次拒绝，未执行
构建或测量。本次已正确保留分配记录工件 `12538856575`，50363 字节，SHA-256
`700c884a539ec271c65a57faf412c433692414152c0ee9d85eb58959902b780d`；API/上传日志一致。
9V74 仍没有独立基线，8370C 也未登记。没有将不同 CPU 的数据替换为原预算，
不再因本次不同分配重启相同采样请求。
