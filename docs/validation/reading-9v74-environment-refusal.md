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
