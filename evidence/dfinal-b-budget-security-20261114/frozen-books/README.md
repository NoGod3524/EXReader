# F08 冻结原书

保留本轮三份英文Project Gutenberg原件，便于上游重生成EPUB后仍可离线重放相同字节。文件逐字节复制自已有冻结书库，未重新打包或修改书内许可；书中保留各自Project Gutenberg许可和说明。用途为原书读取/渲染性能的固定输入。当前URL另经下载核对，同样匹配以下SHA。

| 原件 | bytes | SHA-256 | 原来源 |
|---|---:|---|---|
| pg1.epub — Declaration of Independence | 2444217 | `f9bdcd2a6d3e8008f0a970a545abad2de48f55de8bf12a44c44ee6e42ec2d29c` | https://www.gutenberg.org/cache/epub/1/pg1-images-3.epub |
| pg10.epub — King James Bible | 1717117 | `a873ce9091a8f234e649b773c1a08a00fa4ffa42631d77af30430f005b4799b0` | https://www.gutenberg.org/cache/epub/10/pg10-images-3.epub |
| pg11.epub — Alice's Adventures in Wonderland | 189249 | `4f81245d31380ac1d6eafb9a321e3691369bc70985736ae4bccf849a4f784036` | https://www.gutenberg.org/cache/epub/11/pg11-images-3.epub |

精确spine path由 `tests/reader_perf_windows/render-corpus.json` 固定。基准逐书严格校验SHA；不会用上游新版替换。完成本轮MSVC配置/编译后，在仓库根目录、其他测试完成时运行：

```powershell
python tests/reader_perf_windows/render_budget.py --binary build/audit-msvc/exreader-shell-selection-test.exe --font C:/Windows/Fonts/segoeui.ttf --manifest tests/reader_perf_windows/render-corpus.json --corpus evidence/dfinal-b-budget-security-20261114/frozen-books --out render-replay.json --repeats 3
```

此命令无需联网，输出全部18个独立进程的stdout、原始样本、原书/font/EXE身份和同机相对比值。宿主font、CPU/OS和EXE发生变化应作为新环境记录，不能沿用另一机器的预算。它测量生产有界EPUB render路径；完整产品呈现帧/首次可交互仍缺。
