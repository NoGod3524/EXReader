# 原有 PPTX matrix 首轮失败的只读诊断

输入为首轮原样复制件 `pptx-matrix-first-failed.json`，SHA-256 `40daa5166e7b5dbbc0cae65555530e59f6efd7bfa8099601555e217c6622f536`。没有修改或重跑旧测试；完整独立复算在 `pptx-first-failure-analysis.json`。

`tests/pptx_real_matrix.py:888–893` 原判定同时要求 `max(times) < 200` 及 `median <= 20.5 * 1.5`。本次仅最大值分支失败：`twenty.pptx` 的100次公开渲染样本 median16.2541ms、median ratio0.7928829、nearest-rank p95 77.9284ms；唯一达到或超过200ms的样本是第3页第4次314.9653ms。该页5次原始样本为 `[9.3983,30.7621,10.9606,314.9653,26.7071]`；次大值为第19页第3次166.0238ms。所有页面内容、覆盖和颜色断言通过，matrix文件级结果14/15。

计时边界在 `tests/pptx_real_matrix.py:329–333`：`perf_counter_ns`直接包围公开 `exr_fixed_render`，含C侧bitmap分配；Python bitmap复制/像素oracle/PNG写入发生在计时结束后。每页第1个样本来自原文首次渲染，之后完成内容oracle与图像保存，再做4次原文渲染（`:873–881`）。这100次是墙钟时间，可能包含线程未获调度的时段，不是线程CPU时间。

`CMakeLists.txt:260` 和生成的 `build/audit-msvc/CTestTestfile.cmake:182` 都明确 `RUN_SERIAL=TRUE / TIMEOUT=300`，因此没有证据将本次尖峰归因于CTest并行任务。原始产物没有每次渲染的调度、CPU频率、系统后台活动或PMU数据；一次大尖峰不能证明调度抢占，也不能证明PPTX渲染器内部退化，**根因未知**。

`git diff --quiet e2d6f4d0aa58ea03135f3af1a7d4b9626190fa08 d2b0be6b4e2059bdbb33f0c8f53b137a20189188 -- tests/pptx_real_matrix.py src include CMakeLists.txt` 为exit0；本轮未改这项原测试、200ms/median门槛及SDK源。需要保留首轮失败，再单独运行原测试核对可重现性；单次随后通过不能抹除这次失败或建立根因。
