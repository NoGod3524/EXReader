# 原raw3 iOS候选与只读就绪准备普通合并

状态：指定iPhone/iPad模拟器raw记录UI与保留NULL的原生HTTPS入站范围已同轮通过。独立分支 `codex/reader-apple-raw3-ios-ready`，从records-ready封存 `aab2f207f355d00089a7165aa23e68caf3e5ff6c` 普通merge原raw候选 `72c6bbdd14ebf3be453fa7f0da81119d52675eb5`，无冲突；合并基点 `4749131d722f4f585be767207ed16b32dd9d9b3d`。

原72生产、SDK、七包、全部raw测试与原完整OFF七case、原collector/strict均逐字不变。新隔离driver只改变自身路径定位，并在原erase/boot/bootstatus之后插入固定7c457fb6的只读appearance就绪准备；精确逆投影必须还原72原driver所有业务字节与180/300、raw600及90秒断言预算。新workflow亦精确投影原完整工作流，只重定向实际分支/新守卫/准备driver及新增准备证据复核。

先完整执行每目标原OFF七case，然后原raw六阶段：真实PDF点/range、编辑/删除/恢复/FOUND/跳转/重开、真实终止前后重试、原生HTTPS收12wire/source1/2/NULL、旧v1拒绝与raw重投旧v1仍拒绝。原严格裁判先认证两模拟器同source/run/attempt全部原始工件，再对其已散列认证的准备记录复核。未通过前保留72原失败，不拼旧叶通过。

records-ready独立run40214214442原7×3/native19/SDK2及strict成功只说明准备方案已有实际完整对照，不能替代本合并源码的raw验收。真机、Android实际互通、完整移动同步和产品仍未授。执行、语法、下载解析及证书信任均只在Actions。

## 本合并源码的同轮完整结果

受测source `5ac5e1fa4cf6dcbfe81ea14b9f64b6288470164a`，[run40217963443](https://github.com/NoGod3524/EXReader/actions/runs/40217963443) / attempt1，5作业全部success：SDK iOS `121243123378`、SDK macOS `121243123534`、iPad `121243863572`、iPhone `121243863628`、原strict与准备复核 `121249802254`。

每个移动目标都完整执行原OFF七case，再执行六个原raw/legacy阶段；原严格裁判核对两模拟器的原始ZIP、同source/run/attempt、实际程序/source/链接归属、两prefix和每个原观察。新增准备认证也通过，未使用旧单平台叶结果。

| 真实观察 | iPhone SE第三代 / iOS26.2 | iPad mini A17 Pro / iOS26.2 |
| --- | ---: | ---: |
| 原OFF七case | 7/7 | 7/7 |
| 原raw/legacy阶段 | 6/6 | 6/6 |
| 实际owner观察 | 54 | 54 |
| PDF NUL原点记录 / 非空NUL range | 2 / 1 | 2 / 1 |
| 实际公开FOUND及原/新捕获一致 | 2 | 2 |
| 真实终止前重试created / 终止后created | 1 / 0 | 1 / 0 |
| 原生HTTPS原12wire逐字保持 | 12 | 12 |
| 实收NULL typed行、禁止编辑/跳转 | 1 | 1 |
| source1/2真实UI编辑与恢复 | 均通过 | 均通过 |

两目标均完成256 shard入站一整轮。Mac peer固定受测15dab6b2/run40196978163/attempt1/工件12600789926；实际原DB SHA `4731ac025a34c435b8b7cc50ba128e0c484c736c2fde6d3ae5658593ed9f3389`，NULL revision `2a490dc51d514032a2815e802c8b3f48` / wire SHA `a4d655ded931966dc268f01ab4ffb2717e7c31fb98b3823ad277ef4c2d0c1dbc`，12wire完整父图保留。旧v1失败request在legacy与raw重投后保持原字节/ID，散列与真实重启PID见验收JSON。

原boot/bootstatus后，iPhone只读appearance查询28.125s返回light，iPad5.144s返回light；都在查询就绪后才进入原完整测试，无业务补点。生产对72逐字相等，原默认raw仍OFF、公开MAX2/schema1/wire1不改。本轮未复现原tap失败，不将此单轮结果提升为已确定点击根因或长期稳定性保证。

| 工件 | ID | 字节 | SHA256 |
| --- | ---: | ---: | --- |
| SDK macOS | 12607454469 | 21887243 | `0cd31b77e8cbe268c58ebc94c3357fd98be247f52ed5803f16f6827b8c231cb5` |
| SDK iOS Simulator | 12607854433 | 21891089 | `9771004eb2309a7d9a35ec97a1e1e545f90ef1c8c5a10f45b5116c8acf18b973` |
| iPhone原始 | 12608976777 | 152515213 | `06cf2e467ce225e927b32f36dccf7febe93fc15bc60fc0d5450cfc56b068f49f` |
| iPad原始 | 12608483488 | 186145203 | `2a37546c8d0bbcb8f171e6f2292bb3d2a94fa24e2ea07d4dcdd12ffe07fd7ead` |
| 原strict及准备复核 | 12608502348 | 3514 | `31a6215c9c11e24397adbee25def395b957b40a6428fffd3595cf0a5cc057a62` |

有效期均为 `2027-01-23T17:45:06Z`。原strict在Actions下载两原始ZIP重算大小/散列、核对有效期并重做observation裁判；准备JSON也在原逐文件散列内，随后复核真实命令/设备/查询结果。封存仅改本说明和验收JSON，受测source保持5ac5e1fa。

旧run40201199879的取消、40201417886的iPad新raw预算错误、40203714083的iPhone原OFF两项tap失败均保留；本轮通过不改写那些运行的状态。授予范围仅本轮指定模拟器raw UI及Mac保留NULL入站，Android实际互通、全量移动双向同步、性能、VoiceOver和真机均继续未授。
