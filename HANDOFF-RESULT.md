# S02 Linux 可迁移候选包核验 — 交回状态

状态：**实现已提交，Actions 验收待运行**（`accepted=false`）。

- 固定实现起点：`0889f7d1e9a537c6c1b05456547e016b26e1cd85`
- 分支：`codex/reader-fw-s02`
- 独占路径：`tests/reader_final_s02/`、`.github/workflows/reader-final-s02.yml`、
  `docs/reader-final-s02/`、本文件
- 复用：J24 `contract.py`（`2f5677f1…`）的 seal/extract/walk/tree_problems；
  固定 AT-SPI 客户端（`67e2f8c4…`）；GTK 简洁 producer 的认证原工件（run `40206458217`，
  受测 `57203a52…`，封存 `9fc407a5…`）

契约与判据见 [docs/reader-final-s02/CONTRACT.md](docs/reader-final-s02/CONTRACT.md)，
验收字段见 [docs/reader-final-s02/validation.json](docs/reader-final-s02/validation.json)。
真实受测 SHA、run/attempt/jobs、工件 ID/字节/SHA-256/有效期与逐项结果在 Actions 完成后回填。
