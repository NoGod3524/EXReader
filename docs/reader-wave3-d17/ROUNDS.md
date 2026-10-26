# D17 三轮记录（不拼接验收）

原 D11 `da3ba2d1544edff6dc5004dd9d9d88aa732f9b12` / run `40229380899/1` 保持原样：macOS 15/17，Cancel 前置失败，Apple 独立存储观察缺失。该结果不授予 D17 任何通过范围。

## 第1轮

- 受测 SHA：`9a38aefe56323ef7af8b9944dff6eee55c7f9280`。
- [run40273019034](https://github.com/NoGod3524/EXReader/actions/runs/40273019034)，attempt1；native job121409746910失败，verify job121410582759失败。
- 源码范围/冻结 SDK guard、Python语法、SDK及产品模块构建、fixtures/project成功。
- 自有 `state.cpp` 的 `std::min(size_t,uint64_t)` 在 macOS arm64 编译失败。实际 APP/UI 尚未运行；不是产品错误。独立 verifier 正确拒绝不存在的 actual-app.tar.gz。
- 原ZIP `d17-native-40273019034-1`，ID12629620261，13745518bytes，SHA256 `39250ea78f179b2eb1b92313499f2b2ecc29f7cd988210851e0f48c7a82db00e`，expiry2027-01-24T05:12:57Z；同run/attempt Actions consumer下载、验大小与SHA。
- verification ZIP ID12629286245，1456bytes，SHA256 `cfcba7cac0238967f5abd3672d9c2dd8aeeab71e2c764eba5f79fc20ac7c9a2a`（上传job原始记录；未冒称为原生产ZIP）。
- 返修：uint64_t偏移、显式有界转size_t；不改变任何验收语义。

## 第2轮

- 受测 SHA：`104406d5ab2781b8175b8c51cc795da1acea49f7`。
- [run40273471702](https://github.com/NoGod3524/EXReader/actions/runs/40273471702)，attempt1；native job121411146751失败，verify job121412614217失败。
- SDK、产品、observer和实际APP构建成功，Reading XCTest通过。15项原阅读操作全部通过，并逐项通过独立SDK原件/进度/notes与产品全表/revision/outbox前后检查。
- Cancel在Actions.swift第61行实际enabled/hittable唯一物理控制前置失败；cancel/no_unexpected_revision未授予通过；坏文件拒绝尚未执行。无产品错误结论。
- 原ZIP `d17-native-40273471702-1`，ID12629282263，161209764bytes，SHA256 `fb76242db6fabc7e09bf563d27dbbe8fc89d50e78215f948b2ff3cf558569114`，expiry2027-01-24T05:18:04Z；同轮consumer原ZIP验真。
- APP executable：6938192bytes，0755，非symlink，SHA256 `40f69597c3e8533d9eac113b83a5fe56446b53849825cc75c1fbe72b3f09d94d`；未改权限/重签伪造身份。
- 具体诊断：日志的TouchBar Cancel为 `{{393,-1},{146,32}}`，仍与desktop相交；交集不是完整屏幕可见的证明。末轮要求完整包含，保留enabled/hittable，记录所有候选/完整树，并考虑系统已运行open-panel service。SDK无写断言未减少。

## 第3轮

- 受测 SHA：`3fe7408ac9be417c4571d643c52697efa941bc96`。
- [run40274365720](https://github.com/NoGod3524/EXReader/actions/runs/40274365720)，attempt1。
- 此轮为授权上限；最终结论见 HANDOFF-RESULT-D17.md。不同轮次结果不拼接。
- 末轮已终止：native121413838205失败，verify121415300322失败。Reading XCTest通过，原15阅读操作及18条含setup的实际存储转换检查通过；cancel和全17汇总no_unexpected_revision未完成，坏文件拒绝未运行。
- 最后阻塞是driver新定位路径：`Actions.swift:74`，`NSInternalInconsistencyException: The app representing com.apple.appkit.xpc.openAndSavePanelService could not be found.` 系统running-process存在不等于XCTest可按bundleIdentifier寻址。未能验证完整屏幕包含修正是否解决原Cancel问题；不能将推断写为成功。
- 原nativeZIP ID12630085926，152255314bytes，SHA256 `56039aec1d764054a46a8e9a4fa92e26a6cfbb11ef2a31f29eb26c6fed38a8a2`，expiry2027-01-24T05:28:05Z。
- verificationZIP ID12629129471，10997bytes，SHA256 `c541b08948e43deabf7c2ae313cc391afa9a8fdab9ecf0ade061b79e7e216435`，同expiry。
- `round1.json`、`round2.json`、`round3.json`为相应Actions verifier输出的完整原始文本报告，直接从job日志封存；没有在Dot下载/解压/解析ZIP。
