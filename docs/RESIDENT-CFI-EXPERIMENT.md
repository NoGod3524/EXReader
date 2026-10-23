# 驻留窗口的精确 CFI 后继实验

本实验从 Android 映射受测源码 `19128dc5f5e4a3164416ffa17e63937a3894989b`
独立分叉，分支 `codex/android-restore-cfi`。它改变实验分支 SDK 源码，未采用到
冻结 K `9854061be331fe603a1822d9b2b36ee357154927`、产品宿主、PR8、默认
SDK、版本、ABI 或任何冻结性能预算。旧验收不转授；产品仍使用 K。

## 已定位的缺口

真实失败 Large 第 2 页恢复包含首次 pager 建造、五秒 TextQuote 查询以及超时后
第二次完整建造。超时导致 chapter reader 失败，旧 pager 不可安全继续复用。
`19128dc5…` 的后来同源成功不证明慢路径已修复。原五秒 query 与二十秒 UI
断言保持原样，失败原件继续保留在 Android 映射记录中。

公开 `exr_cfi_point.offset` 是已解码原始 XML 文本的 UTF-16，不是 normalized
UTF-8。仅以 glyph.node 构造 node-start CFI，再附加旧 offset，不能证明精确
位置。仅缓存既往 TextQuote FOUND 也不能解决从未 FOUND 的新保存位置。

## 最小实验能力

新增候选 `exr_pager_cfi_create_at(pager, normalized_offset, control, &cfi, error)`：

- `chapter_reader.text_nodes` 和 immutable index 的 normalized start/end 支持
  二分定位节点；只接受已经完整驻留的 raw text node。
- `chapter_window.c` 的 `text` 累积完整 selected node，`flush` 到节点结束才保存，
  不截出失去 raw UTF-16 前缀的片段；全局 normalized 范围在窗口加载时已核对。
  实际 Large 由 3000 个完整 10 KiB 段落组成，第 2 页不需要猜原始节点前缀。
- 仅重放该 raw node 的 XML 空白折叠，累计 UTF-16 scalar 边界，复用已有
  `exr_cfi_create_for_part`，context=0。实体由现有 Expat 解码，补充字符计两
  UTF-16 单位，组合标记独立计数。
- 非驻留节点、没有明确 raw owner 的人工投影边界返回 `EXR_UNSUPPORTED`；
  UTF-8 scalar 内部返回 `EXR_ARGUMENT`。错误和取消均清空 CFI 输出。
- 生成期间禁止隐式窗口加载。现有 `query_begin` 会 prepare node 0，从后续
  window 回到首单元；新接口单独执行 busy/failed/control 检查，保持旧接口不变。
  若已有 CFI formatter 需要非驻留节点，也拒绝，不允许偷偷全章重放。

未驻留窗口仍有真实缺口：现有 `chapter_window_load` 用 `pump` 完整重放 XML，
并核 `p->global == full node_count`。本实验不增加随机源窗口读取能力，不把有界
内存说成有界总 CPU。现有公开 CFI resolve 仍按其原契约读取必要窗口。

## 独立云端验证出口

`.github/workflows/resident-cfi-experiment.yml` 使用普通与 ASan+UBSan 两个作业：

1. 云端调用原 `write_fixtures`，生成与失败宿主相同的 Large EPUB，使用原 Noto
   字体及相同 600×860、24 字号配置，真正生成第 2 页后直接创建 CFI，不先执行
   TextQuote FOUND；转换前后 windows_loaded/evicted 必须相同。
2. 读取完整非有界文档，把 CFI 解析到 raw node/UTF-16 point；另由 Python
   ElementTree 完整解析原 Large，独立核 normalized point 对应的原始位置。
3. 另一个进程重新打开 EPUB，经原公开 CFI resolve 得到同一 raw point；不做
   全章唯一性扫描、不建立生产缓存。
4. 固定空白／实体／emoji／组合字符的手写 raw offset 预期、scalar 内部拒绝、
   取消、不驻留拒绝、窗口驱逐前后查询与后续分页，以及原 CFI 文本测试。

当前代码尚待独立云端执行；`experimental_only=true`、`product_adopted=false`、
`frozen_sdk_accepted=false`、`budget_credit_seconds=0`。本地只读写源码／文档和
Git，未构建、运行测试、执行语法检查、生成夹具或下载工件。
