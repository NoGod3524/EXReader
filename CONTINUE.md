# 续跑指令（Claude 撞 5 小时限额，转 codex 接着干）

## 你的处境

上一轮是 Claude 会话干到一半撞了 5 小时限额，**代码全在，只是没走完收尾**。

```
工作树   C:\Users\Oscar\Documents\Codex\EXReader-d3-large-20261110
分支     codex/large-book-2-20261110
进度记录 C:\Users\Oscar\Documents\Codex\EXReader-d3-large-20261110\LARGE-OUT.txt
```

## 第一步：先读进度，不要重新规划

```powershell
git log --oneline -6
Get-Content C:\Users\Oscar\Documents\Codex\EXReader-d3-large-20261110\LARGE-OUT.txt -Tail 20
```

进度文件里写了它做到第几步、下一步该干什么、哪些验证还没跑。
**接着干，不要推翻它的方案。**

## 第二步：把剩下的做完

典型剩余工作（按进度文件的实际情况取舍）：

1. 跑完它计划里没跑完的验证（ctest / 真实样本 / 回归）
2. 补它说要补的证据（截图、日志、测量表）
3. 写收尾报告到 `OUT.txt`（Claude 那份是 0 行，因为它在写报告前就被掐了）
4. `git push` 并开 draft PR

## 第三步：不许干的事

- **不要重写**已经工作的代码。它的实现有测试撑着，重写等于丢验证。
- **不要为了让测试过而改断言**。测试红了就查实现。
- 不要动 `tests/check_reading_release.py`（字节被 sha256 绑定，当前应为 `6eb22a30…`）
- 不要在 `tools/version_literal_exceptions.json` 上重排格式（`indent=2`）
- 新增 `src/*.h` 必须在 `tools/layers.json` 登记
- 19 本真书：页数与逐页哈希必须不变

## 第四步：收尾报告要写清

```
① 这一步之前 Claude 做到哪（引用它进度文件的最后一行）
② 你补了什么（逐条）
③ 验证结果：命令 + 实际输出（不许只写"通过"）
④ 没做到的：具体卡在哪一层，还差什么
```

## 特别提醒（每个任务各自的坑）

**d2-media**：MP3/AAC 因为缺 `minimp3.h` 被关掉了（Claude 自己和基线同配置，所以对比有效）。
这个**不要偷偷打开**；如果能在报告里说明"缺哪个头文件、要补齐需要什么"，比强行打开更有价值。

**d3-large**：Claude 发现第一轮 AFTER 测量被负载污染（宿主机 56% CPU、26 个编译进程），
已经写了 `tools/large_book/ab_measure.py` 做交错 A/B 测量抵消负载。
**用它的方法，不要用被污染的那份数据下结论。**

**b1-webdav / b2-opds**：这两条都改 `examples/reader.c` 与 `shell_shelf*.inc`。
**各自在自己分支上做完即可，不要试图合并对方**；集成由主控统一做。

**c2-a11y**：UIA 的 Name/HelpText 已验证生效；剩下的是补实测证据与报告。

