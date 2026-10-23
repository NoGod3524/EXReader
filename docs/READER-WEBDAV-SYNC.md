# 产品WebDAV同步：不可变原件与修订

本模块接续[离线revision/outbox](READER-REVISION-WIRE.md)，只负责Windows/Linux的
原件与修订传输、完整性和发现。宿主仍负责安全凭据、调度、SDK导入、实体projection和冲突UI。

## 固定远端布局

用户配置的HTTPS集合下面建立独立命名空间：

```text
exreader-sync-v1/
  objects/00/ ... objects/ff/
    <original-sha256>.<format>
  revisions/00/ ... revisions/ff/
    <revision-uuid32>-<exact-wire-sha256>.json
```

objects按原件SHA首字节分片，revisions按UUID首字节分片。一个发现列表只访问一片，
Depth:1、最多2000项／4 MiB；超限拒绝，不截断。每命名空间256片对应512000项的
硬发现上限；偏斜分布可能先触单片上限。相近容量上的并发发布可能使下一次列表拒绝，
不能把该错误算成完整同步。目录缺失只代表本次扫描为空，不删除本地记录。

`reader_sync_step(shard,after,limit,...)`每次最多发布100条outbox、读取100份修订。
报告给出本片剩余项、continuation、next_shard和pending；宿主必须覆盖全部256片并重启扫描，
才能发现游标之前的并发插入。API的`full_library_complete`始终为false，单片成功不授予全库同步。
原件／历史不自动回收；不上传SQLite、WAL或SHM。

## 发布与恢复

原书引用只使用公开全局book key。`reader_revision_book_identity`重新校验已保留book历史，
取得唯一一致的原件长度；没有非删除metadata返回NOT_FOUND，冲突返回错误，不按时间选值。
非book引用缺少该信息时，local outbox保留pending，不把长度假设为0。

上传前把宿主原书流式复制到私有快照，以64 KiB块核长度与SHA。先以
`PUT If-None-Match: *`发布原件，再发布引用它的修订。创建成功、412与连接在响应前中断，
均须重新GET并验证长度／SHA才继续；修订也须GET核对原始wire身份才ack。
远端损坏不能覆盖本地原件或清空队列；模块不执行远端覆盖、MOVE或DELETE。

远端修订先按文件名ID／SHA与v1协议验证，再保留到history。
缺book metadata的非book修订仍保留，报告pending，下个完整扫描再次验证原件。
所有原件均核独立已知长度和SHA；通过后才保留为私有`<sha>.<format>`缓存。
并发头、失序父与墓碑沿用一期规则；传输不写projection、SDK或当前阅读位置。

进程终止前后的history/outbox由SQLite事务恢复；远端提交、本地ack之前被终止时，
下一进程重新条件发布并核远端原件。强制终止可能留下私有暂存文件，宿主可在确认没有
活动同步后清理`.reader-sync-*.tmp`；本模块不删除其他进程可能仍在使用的文件。
私有目录须由宿主保证稳定、不可被外部写入；模块以系统SHA实现流式核验（Windows BCrypt、
Linux OpenSSL Crypto），不把整本书读入内存。

## 安装与宿主入口

依次安装产品catalog、revision 0.2.0、WebDAV 0.2.0和本模块。
使用`find_package(EXReaderSync CONFIG REQUIRED)`及`EXReaderSync::reader_sync`，
包含C头`reader_sync.h`。create接收借用的WebDAV client、revision store、私有目录和原件resolver；
step只在创建它的工作队列调用，拒绝回调重入。凭据由WebDAV client临时持有，
不进入wire、产品DB、任意服务错误正文或本模块日志。

TLS／同源同根规则复用已交付来源模块；只读GET/PROPFIND保留其受限重定向行为，
MKCOL/PUT一律不跟随重定向。WinHTTP/curl均保持系统证书和主机名验证。

云端验收尚在执行；本期不授予移动端、macOS、真实云盘互操作、UI、安全存储、
实体联合事务或产品完成。
