# T05：八个已复审模块的共同安装与实际组合

先读[共同约束](README.md)。从 `e4356a6e13223469fdf3b2f3d5171a6e99ab10a6` 创建 `codex/dot-reviewed-composition`。目标是消除各包独立绿、装到一起却失败的风险，只负责组合验证，不修改宿主或这些模块的实现。

## 唯一允许普通merge的交付

- cloud-import：`0d07d23bf53cd288de7a0af152d48553c18be241`
- bulk-organization：`757249aaed9a1dc6be981354f6af97e813233f04`
- link-policy：`4175e1de8e61ebc68dc4a1313e32408a4956f1c7`
- jump-history：`561208ede9e85263c98e9563470349c7fa39ccb5`
- keyboard-actions：`74804bbfff63fdc65d3e07037a8138cefff1cf75`
- book-information：`723cd5e7f9849fe050f2159a9f3a125848cdbec4`
- sync-status-view：`0bcb4d06bbeab6dd844954b19ee979e4bede50bd`
- account-profiles：`a0746156b37db7cd750fb805899a616ef2c6a80f`

先读各包CMake/公开头与docs及中央root复审，取真实包名/目标名；不要按目录名猜API。将这八份交付普通merge到固定起点，记录确切合并点。守卫要求后续 apps/examples/extras 与该合并点逐字相同、每个模块树与其交付相同；若普通merge发现实质生产冲突，交root精确冲突，不能自行更改跨owner实现。

## 必须交付

沿用当前三桌面18包one-prefix验证，把八包和其公开依赖装进同一可重定位前缀。新鲜目录里的C11/C++消费者只find_package安装包，覆盖公开头共存、唯一SDK/产品SQLite provider、依赖传递、移动前缀后重编译运行、原reading默认安装不混入可选包。

每包原安装消费者与有意义的原判据继续执行；平台专属native事件/IME的skip如实保留，不能为组合验证声称已测。增加一个真实共用产品owner/session的贯通场景：云盘下载→SDK owner侧载与原件回读→现有产品映射→批量favorite→只读book-info/sync-status→公开reading capture+history回跳；快捷键/外链使用实际公共函数参与但不自动打开外部站点。需要具体非同线程能力时尊重原owner，不能发明第二套产品映射或共享SDK连接到网络worker。

没有公共接口能够完成某一段时，给出头文件/签名/最小复现的具体缺口，先完成可独立验证部分，并让整体accepted=false，不能用手写SQL补链。

保留当前18包原判据、默认prefix隔离、搬迁、重复SQLite/泄漏include等门禁。三平台同source/run/attempt严格汇总，绑定真实C/C++消费者与每包报告。性能和实际宿主UI不在本包授予范围。

## 可修改路径（普通merge后）

- `tests/reader_reviewed_composition/**`
- `.github/workflows/reader-reviewed-composition.yml`
- `docs/READER-REVIEWED-COMPOSITION.md`
- `docs/validation/reader-reviewed-composition.json`

各独立包及已有tests/workflows保持字节相同；只在新tests目录组合原判据与新场景，不删旧失败。
