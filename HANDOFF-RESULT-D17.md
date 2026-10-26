# D17 最终交回：15/17，拒绝完整验收

**三轮上限已用完，无第4轮。** 最终同一source/同run/同attempt的15项阅读操作及其独立存储边界通过。实际picker Cancel仍被驱动前置异常阻塞；全17汇总、实际坏文件picker拒绝未完成，`accepted=false`。未发现/未宣称产品错误，不应作为已完成D17合入。

## 不可变身份

- 功能分支：`codex/reader-wave3-d17`；固定seed：`d263ce5228838ac90c0a0dc13a5193d4a7739681`（不是已验收生产BASE）。
- **最终受测完整SHA：`3fe7408ac9be417c4571d643c52697efa941bc96`**；tree：`76738ff953ea403e8c79a82adabd933b790bfd6e`。
- [最终run40274365720](https://github.com/NoGod3524/EXReader/actions/runs/40274365720)，attempt1；native job121413838205失败，verify job121415300322失败，均终态。
- SDK源码：`edddc463c06ed5731195cdb8f06b2df6dff7699e`；新guard证明include/src/bindings未变，当前source重新构建实际SDK及宿主，未拼旧APP/SDK测试结果。
- 文档HEAD：包含本文件的独立 `[skip ci]` 提交，parent为上述受测SHA；其完整SHA在最终回信与工作区D17-status.md中记录。文档不冒称被功能测试覆盖。
- 提交作者：Yinuo Xu。普通HTTPS git push缺凭据、确认未执行后，采用已授权Git Data API，仅发布指定功能分支；本地同树提交通过rebase去重对齐，未reset原工作树。

## 原工件与实际程序

|工件|ID|原ZIP bytes|SHA-256|有效期UTC|
|---|---:|---:|---|---|
|d17-native-40274365720-1|12630085926|152255314|`56039aec1d764054a46a8e9a4fa92e26a6cfbb11ef2a31f29eb26c6fed38a8a2`|2027-01-24T05:28:05Z|
|d17-verification-40274365720-1|12629129471|10997|`c541b08948e43deabf7c2ae313cc391afa9a8fdab9ecf0ade061b79e7e216435`|2027-01-24T05:28:05Z|

原nativeZIP由同run/attempt Actions consumer下载、校验原始bytes/SHA/expiry/source、逐文件绑定和实际app tar核验。verificationZIP身份来自原上传job及独立API元数据，不冒称为生产ZIP，也未在Dot下载。消费者运行时自身job自然为in_progress；封存前另查两job终态。

APP：`EXReaderHost.app/Contents/MacOS/EXReaderHost`，6938192bytes，SHA256 `40f69597c3e8533d9eac113b83a5fe56446b53849825cc75c1fbe72b3f09d94d`，0755、非symlink，上传前记录；tar保留属性。Info.plist内EXRSourceSHA为最终受测SHA。与第2轮可执行字节相同符合产品源码未变，但本轮APP及所有证据均重新构建/运行/验证，不复用第2轮通过范围。完整app tar、xcresult、截图、AX树、原生日志、SDK identity、observer、每步snapshots在nativeZIP内。

配置：macos-15-arm64，SDK3.41.0，PAGE_THEME=ON，RAW3=OFF，无HOST_REVIEW/IMPORT_REVIEW，CODE_SIGNING_ALLOWED=NO。SDK观测独立进程仅调用公共读取API；产品catalog单独mode=ro/query_only；每份快照重复读取相等后封存，不读取SDK内部SQL、不调用写API。

## 精确通过范围

通过15项：`back`、`resume`、`import`、`next`、`previous`、`search`、`directory`、`records`、`settings`、`close.search`、`close.directory`、`close.records`、`close.settings`、`disabled_noop`、`continue_after_return`。

这些操作及3项setup共有18条已完成转换，每条均有实际操作前/后的SDK原件SHA/字节数、progress、notes及产品所有表原值（含reader_books/local_books/revisions/outbox）。

- import：真实fixture按钮入口，SDK新增实际Sample.epub原件，并新增一致的产品/local映射；无revision/outbox增写。实际SDK原件还逐项绑定本轮 authored Sample.epub bytes。
- next/previous/continue：持久SDK progress实际改变；原件/notes/产品全表不变。
- 其余已完成操作：SDK原件/progress/notes与产品全表逻辑状态不变；disabled Find为真实点击后仍disabled、状态/输入未变。
- 语义沿用D11：import是fixture原生入口；settings仅阅读主题；resume是实际重开书，不授予独立Continue按钮、完整设置或任意生产picker成功导入。

## 保留失败和缺口

1. `cancel`仍pending并有失败XCTest，不能叫通过。最后失败位于自有 `Actions.swift:74`：`NSInternalInconsistencyException: The app representing com.apple.appkit.xpc.openAndSavePanelService could not be found.` NSRunningApplication列出service，不等于XCTest可按bundle ID寻址；这是driver错误，未证明产品取消写入错误。
2. 第2轮已观察到TouchBar Cancel `{{393,-1},{146,32}}`与屏幕有交集；第3轮改为完整包含以排除别名，但新service查询先抛异常，尚不能证明这一修正解决原D11问题。
3. `no_unexpected_revision`全17汇总不通过；已执行15项的独立无写/应写证明不补齐未执行Cancel。
4. `reject_existing_broken`真实既存坏EPUB选择/提交尚未运行；绝未用不存在文件伪装取消。
5. modal键盘焦点、物理键盘/设备、screen reader、签名/发布、完整产品均不授予通过。未改D15/SDK/原D11/旧guard/预算；没开PR、没改默认分支、没tag/Release。

需继续时，应先另行授权超过3轮的驱动修复与验证：保留当前失败，移除“running service即XCTest可寻址”的错误假设，基于host的完整AX树或公有Accessibility API定位实际panel。不能只删失败用例、降低enabled/hittable、或把本轮15项拼上其他source取消结果。

## 接入与证据入口

- `tests/reader_wave3_d17/`：driver、独立observer、新scope guard、严格consumer。
- `.github/workflows/reader-wave3-d17.yml`：唯一新workflow。
- `docs/reader-wave3-d17/ROUNDS.md`、`round1.json`、`round2.json`、`round3.json`：全部失败及原始consumer报告。
- 原D11 `da3ba2d1544edff6dc5004dd9d9d88aa732f9b12` / run40229380899/1保持原样。

仅供协调者审查/接入自有路径，不代表合格验收（本会话未执行接入）：

```bash
git fetch origin codex/reader-wave3-d17
git cherry-pick 9a38aefe56323ef7af8b9944dff6eee55c7f9280 104406d5ab2781b8175b8c51cc795da1acea49f7 3fe7408ac9be417c4571d643c52697efa941bc96
# 文档封存单独 cherry-pick 最终回信给出的 docs HEAD。
```

本地只进行源码/文档/Git；全部构建、语法、fixtures、UI、截图、artifact下载/解包/核验在GitHub Actions。没有创建/调用Codex、电脑任务接口、cpuse或子代理。
