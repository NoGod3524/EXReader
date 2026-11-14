# PDF-HYBRID-M1 实测报告

基线：`6adcf2b5`。Windows x64 / GCC 16.2.0 / Release / PDF_CRYPTO=ON。

公开打开路径原已连接同一 hybrid 解析器；本次补齐文件级和逐页渲染验收、解析证据及加密冲突警告。公开 API 为 `exr_fixed_open/pages/render`，私有 `exr_pdf_open` 接收内存字节。

6 份原始 Microsoft 365 COM 导出，29 页，全部成功且每页非白像素 > 0。14 组新增 CTest 全部通过。

## Office manifest 与实测

| 文件 | Producer | bytes | 引擎/manifest 页数 | 渲染/失败 | 非白像素合计 | /XRefStm 偏移 |
|---|---|---:|---:|---:|---:|---:|
| pptx-1.pdf | PowerPoint | 30649 | 1/1 | 1/0 | 17604 | 29382 |
| pptx-20.pdf | PowerPoint | 60423 | 20/20 | 20/0 | 352822 | 54480 |
| word-5.pdf | Word | 33032 | 5/5 | 5/0 | 23932 | 28232 |
| excel-1.pdf | Excel | 23638 | 1/1 | 1/0 | 13523 | 17761 |
| chinese.pdf | PowerPoint | 24458 | 1/1 | 1/0 | 18127 | 23078 |
| image-only.pdf | PowerPoint | 9250 | 1/1 | 1/0 | 28591 | 8153 |

完整 SHA-256（与入库文件逐字节核对）：

| 文件 | SHA-256 |
|---|---|
| pptx-1.pdf | `6126d0dabe42f0b518c8e92410389189d68fde97ef87ecd76cbed49f585d5df5` |
| pptx-20.pdf | `2bfb94aa6905f27915e309b3c820fef3ba13492dddedfb93d97a10e8d7679729` |
| word-5.pdf | `5e7214f0700df85cdb96fbccdcb303461f0b43a08278893ba8fd098025e90aff` |
| excel-1.pdf | `3621e313f1c823a01e8242f21f3d83e800f86a975299f4432f41287b65e499e0` |
| chinese.pdf | `857238af6f4c9bd422e0a1d30b4b1e3c1bdb6f2a30382227a972ed10cb3ec5d2` |
| image-only.pdf | `c400b3aa82018e7ba4dcce56817ed01d5d4ca0ab7bda74f3df06fa3e533ccb66` |

逐文件解析器实测证据与逐页结果：

### pptx-1.pdf

```text
parser discovered /XRefStm offset=29382 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=480 height=270 nonwhite_pixels=17604
rendered=1 failures=0 nonwhite_pixels_total=17604
```

### pptx-20.pdf

```text
parser discovered /XRefStm offset=54480 sections=1 encrypt_conflicts=0
public open status=0 pages=20 expected=20
page=1 status=0 width=480 height=270 nonwhite_pixels=17604
page=2 status=0 width=480 height=270 nonwhite_pixels=17626
page=3 status=0 width=480 height=270 nonwhite_pixels=17629
page=4 status=0 width=480 height=270 nonwhite_pixels=17619
page=5 status=0 width=480 height=270 nonwhite_pixels=17631
page=6 status=0 width=480 height=270 nonwhite_pixels=17631
page=7 status=0 width=480 height=270 nonwhite_pixels=17613
page=8 status=0 width=480 height=270 nonwhite_pixels=17637
page=9 status=0 width=480 height=270 nonwhite_pixels=17630
page=10 status=0 width=480 height=270 nonwhite_pixels=17656
page=11 status=0 width=480 height=270 nonwhite_pixels=17633
page=12 status=0 width=480 height=270 nonwhite_pixels=17654
page=13 status=0 width=480 height=270 nonwhite_pixels=17651
page=14 status=0 width=480 height=270 nonwhite_pixels=17652
page=15 status=0 width=480 height=270 nonwhite_pixels=17656
page=16 status=0 width=480 height=270 nonwhite_pixels=17661
page=17 status=0 width=480 height=270 nonwhite_pixels=17640
page=18 status=0 width=480 height=270 nonwhite_pixels=17661
page=19 status=0 width=480 height=270 nonwhite_pixels=17660
page=20 status=0 width=480 height=270 nonwhite_pixels=17678
rendered=20 failures=0 nonwhite_pixels_total=352822
```

### word-5.pdf

```text
parser discovered /XRefStm offset=28232 sections=1 encrypt_conflicts=0
public open status=0 pages=5 expected=5
page=1 status=0 width=306 height=396 nonwhite_pixels=4785
page=2 status=0 width=306 height=396 nonwhite_pixels=4788
page=3 status=0 width=306 height=396 nonwhite_pixels=4786
page=4 status=0 width=306 height=396 nonwhite_pixels=4785
page=5 status=0 width=306 height=396 nonwhite_pixels=4788
rendered=5 failures=0 nonwhite_pixels_total=23932
```

### excel-1.pdf

```text
parser discovered /XRefStm offset=17761 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=306 height=396 nonwhite_pixels=13523
rendered=1 failures=0 nonwhite_pixels_total=13523
```

### chinese.pdf

```text
parser discovered /XRefStm offset=23078 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=480 height=270 nonwhite_pixels=18127
rendered=1 failures=0 nonwhite_pixels_total=18127
```

### image-only.pdf

```text
parser discovered /XRefStm offset=8153 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=480 height=270 nonwhite_pixels=28591
rendered=1 failures=0 nonwhite_pixels_total=28591
```

统计口径：scale=0.5，alpha 非零且任一 RGB 通道 <250 的像素；白底不计入。未跳过任何失败页。真实语料没有 stderr 警告，无需字体白名单豁免。

## 构造边界实测

任务列举的边界包含 5 类正常场景和 3 类坏输入；全部覆盖，未按验收段落的“4+2”删减。纯 Python 标准库生成，RC4 内容确实加密。

### incremental.pdf

```text
file=incremental.pdf bytes=1146 sha256=3c268780387813f4a2133e889172bebe43d110835483332d127c305c01589e22
parser discovered /XRefStm offset=716 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=120 height=120 nonwhite_pixels=4900
rendered=1 failures=0 nonwhite_pixels_total=4900
```

### free-entry.pdf

```text
file=free-entry.pdf bytes=726 sha256=8d7461a2f40f83a7fe0bd9da3d80a32281252baa66c78dd368d91818174531fd
parser discovered /XRefStm offset=306 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=100 height=100 nonwhite_pixels=4900
rendered=1 failures=0 nonwhite_pixels_total=4900
```

### objstm.pdf

```text
file=objstm.pdf bytes=792 sha256=a42165244be1a9232e46488f93def10bcec5d79f09678350c0f0679f33d3a69a
parser discovered /XRefStm offset=372 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=100 height=100 nonwhite_pixels=4900
rendered=1 failures=0 nonwhite_pixels_total=4900
```

### encrypted-conflict.pdf

```text
file=encrypted-conflict.pdf bytes=1088 sha256=d079002eee0ac5ae771b0a9609f3c3c697a787ebd0dbac6a971c02152b2b96fe
parser discovered /XRefStm offset=564 sections=1 encrypt_conflicts=1
public open status=0 pages=1 expected=1
page=1 status=0 width=100 height=100 nonwhite_pixels=4900
rendered=1 failures=0 nonwhite_pixels_total=4900
same /Encrypt identity: status=0 warnings=0 rendered=1
PDF warning: hybrid /Encrypt conflict; using classic trailer /Encrypt
PDF warning: hybrid /Encrypt conflict; using classic trailer /Encrypt
```

### linearized.pdf

```text
file=linearized.pdf bytes=1062 sha256=a5b893f009a412a543896c28f5e9b6d0ceeb5668b1bf871cf2b30115f77c16da
parser discovered /XRefStm offset=877 sections=1 encrypt_conflicts=0
public open status=0 pages=1 expected=1
page=1 status=0 width=100 height=100 nonwhite_pixels=4900
rendered=1 failures=0 nonwhite_pixels_total=4900
```

### bad-truncated.pdf

```text
file=bad-truncated.pdf bytes=724 sha256=5239a719ae57bce305ae790ecb7a130a6b39f60e93233ffee683edee04073fee
parser status=5 EXR_FORMAT message=Invalid PDF indirect object or stream bounds
public open status=5 EXR_FORMAT message=Invalid PDF indirect object or stream bounds
```

### bad-width.pdf

```text
file=bad-width.pdf bytes=726 sha256=56e3209aed9f6a8763f11bb94da72826750e8b80e1a6bcaf9f7ef4398c813554
parser status=5 EXR_FORMAT message=Invalid PDF cross-reference stream
public open status=5 EXR_FORMAT message=Invalid PDF cross-reference stream
```

### bad-index.pdf

```text
file=bad-index.pdf bytes=727 sha256=71c69c50032c6af3a5e5b628fbf4870b8c95229cbc6103743ff4b19dab547239
parser status=5 EXR_FORMAT message=Invalid PDF cross-reference stream
public open status=5 EXR_FORMAT message=Invalid PDF cross-reference stream
```

增量更新最终页面为 240×240（scale=0.5 输出 120×120），旧版为 200×200；测试明确断言最终尺寸。free-entry 和 objstm 将必需的 Page 对象仅保存在补充索引中，前者经典 free 项的 next=3。

加密冲突选择经典 trailer 的 `/Encrypt 7 0 R`；补充流 `/Encrypt 8 0 R` 指向不支持的字典。实际内容成功解密，并保留冲突计数 1。原始输出中警告出现两次，因为分别进行了私有解析探针和公开打开。相同字典身份的对照样本渲染成功且无警告。

## 验证命令与原始输出

```powershell
cmake --build build -j 12
ctest --test-dir build -R 'native-pdf-hybrid-(real|edge)-' -V
$env:PYTHONUTF8='1'
ctest --test-dir build -E 'sdk-release|sdk-doc-coverage' --output-on-failure -j 8
& 'C:/Users/Oscar/OneDrive/Desktop/deepseekHarness/ops/prepush-check.ps1' -Worktree $PWD
```

[逐文件逐页原始输出](matrix-raw.txt) · [新增 CTest 输出](hybrid-ctest.txt) · [全量 CTest 输出](ctest-full.txt) · [prepush 输出](prepush.txt)

全量：`100% tests passed out of 577`。

prepush：无冲突标记、code/docs 结构扫描、check_sdk_docs.py 全部通过（exit=0）。`tests/check_reading_release.py` 未修改。

## 文档改动与已知边界

`docs/NATIVE_VALIDATION.md` 新增 PDF-HYBRID-M1 节并明确“hybrid PDF 现已接入页面渲染”；S039/S040/S041 的未连接描述保留为当时状态，并指向当前验收。

- 线性化用例验证双 xref、向前 `/Prev`、hint 流及 hybrid 索引的顺序打开/渲染；不实现或认证按 hint 的网络分段读取。
- 加密冲突实测覆盖 R2/RC4、空用户密码；未穷举 AES R3–R6 与多 revision hybrid 的组合。现有独立 crypto 测试仍运行。
- Office 语料代表本机 Microsoft 365 导出，不代表所有历史 Office 版本；字体轮廓不作跨宿主像素等同断言。
- 解析器既有对象/展开预算、外部引用及不支持的图像编解码错误仍适用。

本次没有新增绝对毫秒性能门槛。

语料复现：先运行 `tools/generate_pdf_hybrid_office.ps1`，再运行 `python tests/make_pdf_hybrid_fixtures.py --office`。临时 Office 源文件保留在 `build/pdf-hybrid-office/`，入库 PDF 为未经重写的 COM 原始导出。原始内容与构造语料均为本项目原创测试内容（MIT）。
