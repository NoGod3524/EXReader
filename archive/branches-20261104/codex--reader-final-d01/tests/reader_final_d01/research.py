"""Second-pass route/owner research. Distinguishes partial paths from capability acceptance."""
from catalog import ENTRIES,GUARDS,BASE
WROOT='examples/reader.c'; WM='apps/reader/desktop/windows_import_organize_ui.inc'; WR='apps/reader/desktop/windows_records.inc'
L='examples/linux/reader.c'; LR='examples/linux/reading.c'; LA='examples/linux/accounts_ui.inc'
A='examples/android/app/src/main/java/org/exreader/host/MainActivity.java'; AC='examples/android/app/src/main/java/org/exreader/host/ImportController.java'; AS='examples/android/app/src/main/java/org/exreader/host/SyncPanel.java'
S='examples/apple/HostViews.swift'; SM='examples/apple/HostModel.swift'; SA='examples/apple/HostAccountViews.swift'; SR='examples/apple/HostReadingRecordViews.swift'
EXTRA={
'Windows':{
'R08':(WM,'L"加入子书架"','加入子书架','书库 > 批量整理… > 明确动作 > 加入子书架 > 选择现有组 > 应用到选中书籍','winio_go','winio worker / 产品库；只证现有组成员操作，不证新建子架'),
'R09':(WM,'L"加入标签"','加入标签','书库 > 批量整理… > 明确动作 > 加入标签','winio_go','winio worker / 产品库'),
'R10':(WM,'L"加入系列"','加入系列','书库 > 批量整理… > 明确动作 > 加入系列','winio_go','winio worker / 产品库；系列排序编辑另需证据'),
'R14':(WR,'L"保存位置(&P)"','保存位置','阅读 > 书签与阅读记录… > 保存位置','winrecords_capture','reading records owner / 产品进度修订；本地自动进度另经save_progress'),
'R17':('apps/reader/desktop/windows_preferences_ui.inc','L"阅读设置(&R)…\\tCtrl+,"','阅读设置','设置 > 阅读设置… / Ctrl+,','prefs_show','preferences owner / 设置文件'),
'R18':(WROOT,'static exr_status job_open(host_job *job)','书名（动态）','断网后书架选择已有本地书 > 打开；沿实际job_open读取SDK source','job_open','SDK owner / 本地原件；离线生命周期仍未执行'),
'R19':(WR,'L"存在冲突"','存在冲突 / 恢复','阅读 > 书签与阅读记录… > 冲突记录 > 恢复','winrecords_state','reading records owner / 保留版本；不等价全metadata冲突解决器'),
'R20':(WROOT,'static int save_progress(void) {','正常关闭/重开（无新增按钮）','正常关闭 > 重开 > 打开原书；读取SDK progress','save_progress','SDK owner / 本地进度；崩溃恢复须单独实测'),
'R22':(WROOT,'exr_library_import_source_unique(g.library','导入书籍…','重复及损坏文件沿R01实际导入入口','exr_library_import_source_unique','SDK unique import / 产品映射；所有格式错误路径尚未运行'),
'R23':('apps/reader/desktop/windows_accounts_ui.inc','L"同步失败，已保留已完成的部分。可点击“重试”继续。"','重试','同步账号… > 应用测试授权 > 立即同步 > 错误后重试','acct_tick','account session owner / 状态与安全凭据')},
'Linux':{
'R14':('examples/linux/reading_records_ui.inc','G_CALLBACK(records_save_progress)','Save progress','Reading records… > Save progress','records_save_progress','records worker / 产品进度；自动本地进度经reading.c persist'),
'R18':(LR,'static exr_status persist(','书名（动态）','断网 > Shelf F2 > 打开已有本地书；open_book读取本地SDK','open_book','linux_reader owner / 本地SDK原件与进度'),
'R19':(LA,'static void accounts_present_conflicts(','Version conflict','More > Account / Sync… > 同步后冲突列表 > 版本条目','accounts_present_conflicts','received owner / revision heads；不是自动覆盖解决'),
'R20':(LR,'exr_library_progress_get(reader->library','正常关闭/重开（无新增按钮）','关闭 > 重开 > Shelf F2 > 原书；open_book读取保存位置','open_book','linux_reader owner / 本地SDK；故障恢复需实际杀进程'),
'R21':(L,'if(event->keyval==GDK_KEY_Escape)','Cancel / Escape','系统选择器Cancel；工作中Escape（非正在保存设置）','action(NULL,"cancel")','generation cancellation / 已接纳进度保留'),
'R22':(LR,'exr_library_import_source_unique(reader->library','Import','Import F1选择重复/损坏文件；沿unique import','exr_library_import_source_unique','linux_reader owner / SDK去重'),
'R23':(LA,'Sync could not start. Your saved library was kept','账号错误状态','More > Account / Sync… > 测试账号同步失败 > 重试','accounts_notice','account session owner / 保留本地库')},
'Android':{
'R02':(A,'Intent intent = ImportEntry.pickerIntent(true);','Import','Import > Android系统DocumentsUI > 已安装测试Provider > 选择文件','startActivityForResult','ImportEntry + ImportController / URI暂存；Provider可用性外部依赖'),
'R14':('examples/android/app/src/main/java/org/exreader/host/ReadingPanel.java','"保存进度"','保存进度','阅读更多操作 > 阅读记录 > 保存进度','NativeReadingProduct.PROGRESS','native reading owner / 产品进度；自动本地页进度经persistPage'),
'R18':(A,'private void openBook(long id, long offset, int page)','书名（动态）','断网 > 书架点击已有本地书，沿openBook','openBook','single host worker / BookStore本地原件'),
'R19':(AS,'这本书的同步记录需要先解决冲突或恢复','这本书的同步记录需要先解决冲突或恢复','More > 同步 > 云盘书目 > 冲突书籍','book.receivable()','SyncController / 显示冲突并拒绝接收；未提供此处一键解决'),
'R20':(AC,'List<ReadyRequest> recovered = opened.pendingReady();','Refresh','冷启动恢复pendingReady；书架Refresh重试','pendingReady','ImportController / staging与Ready leases；运行边界尚未验'),
'R22':(A,'else startImport();','Import','按R01分别选择重复/损坏测试文件','startImport','ImportController → single SDK owner / 精确去重与错误回传'),
'R23':(AS,'"仅本次使用"','账号 / 仅本次使用','More > 同步 > 账号 > 输入测试错误授权 > 仅本次使用 > 立即同步','controller.configure','SyncController / Keystore或会话凭据；真实故障待验')},
'Apple':{
'R02':(S,'.fileImporter(isPresented:','打开文件…','系统文件选择器 > 已安装测试云盘位置 > 选择文件；不是WebDAV账号入口','model.importFile','security scoped URL → HostReaderModel owner；第三方Provider待验'),
'R03':(SA,'HostAccountChooser(accounts: accounts)','本地书库 / 云盘书库','顶栏本地书库/云盘书库 > 账号面板 > 连接；主界面同步','HostAccountChooser','HostAccounts + HostSyncControls / Keychain、独立产品库'),
'R14':(SR,'model.saveReadingRecord(bookmark: false)','保存阅读进度','阅读ellipsis > 阅读记录 > 保存阅读进度','model.saveReadingRecord','HostReadingRecords owner / 产品进度；本地状态经persistNow'),
'R18':(SM,'func open(bookID: Int64, cancel: HostCancelBox)','书名（动态）','选择本地书库 > 断网 > 书架已有书名 > 打开','open(bookID','HostSession / library本地source；离线未实测'),
'R19':(SR,'model.showReadingHistory(row)','保留版本','阅读ellipsis > 阅读记录 > 保留版本 > 明确恢复','model.showReadingHistory','HostReadingRecords / revision history；不代表全产品冲突UI'),
'R20':(SM,'func persistNow()','正常关闭/重开（无新增按钮）','切后台/关闭触发persistNow；重开原书','self.session?.persistCurrent()','HostSession owner / SDK进度+writeState；崩溃场景待验'),
'R22':(SM,'let (bookID, created) = try session.importBook','打开文件…','实际系统选择器选择重复/损坏文件，沿session.importBook','session.importBook','HostSession / SDK unique import与catalog；错误不能更改旧书'),
'R23':(SA,'Button("更新授权")','更新授权','顶栏账号选择器 > 测试账号更新授权 > 重新同步','updating = profile','HostAccounts / Keychain；账号不可用与保留本地库待验')}
}
for family,rows in EXTRA.items():ENTRIES[family].update(rows)
GUARDS['Windows'].update({'R08':['EXR_READER_WINDOWS_IMPORT_ORGANIZE'],'R09':['EXR_READER_WINDOWS_IMPORT_ORGANIZE'],'R10':['EXR_READER_WINDOWS_IMPORT_ORGANIZE'],'R14':['EXR_READER_WINDOWS_RECORDS'],'R17':['EXR_READER_WINDOWS_PREFERENCES'],'R19':['EXR_READER_WINDOWS_RECORDS'],'R23':['EXR_READER_WINDOWS_ACCOUNT']})
GUARDS['Linux'].update({'R14':['EXR_READER_READING_RECORDS_UI'],'R19':['EXR_READER_ACCOUNT'],'R23':['EXR_READER_ACCOUNT']})
GUARDS['Android'].update({'R14':['READER_READING'],'R19':['READER_SYNC'],'R23':['READER_SYNC']})
# Explicit remaining gaps: classify after reviewing route/source boundaries, not
# simply because no registry tuple was authored. Per-platform rows carry these.
GAPS={
'R04':dict(classification='external_system_workflow',reason='Product plan uses Android system file transfer / Apple file sharing / desktop local files. No in-app USB controller; cable transfer requires real OS/device evidence. Import after transfer is R01, not proof of cable.',files=['docs/READER-PRODUCT-PLAN.md'],anchors=['有线导入先使用Android系统文件传输和Apple文件共享']),
'R24':dict(classification='module_only_no_host_route_established',reason='reader_ld_remove/recover/reimport public module exists. Reviewed host sources do not call reader_ld_; delete-book UI cannot substitute for remove-local-download. Host wiring must be supplied by owner; environment disposal is separate manual cleanup.',files=['apps/reader/local-downloads/include/reader_local_downloads.h'],anchors=['reader_ld_remove']),
'R05':dict(classification='module_available_no_matching_host_route',reason='Batch-import module exists but reviewed host entry is single/file-only input, not a folder chooser. Android pickerIntent and Apple fileImporter are not folder batch integration; Windows compact system picker also selects files.',files=['apps/reader/batch-import/README.md'],anchors=['reader_batch_enumerate_*']),
'R06':dict(classification='adapter_available_no_matching_host_route',reason='Desktop drop adapter exists, GTK explicitly wires file_input_attach. No equivalent route established in reviewed Windows/Apple/Android host scopes; file selection is not drag/drop.',files=['extras/desktop-drop/include/exr_desktop_drop.h'],anchors=['immutable, bounded exr_drop_request']),
'R08':dict(classification='catalog_module_not_host_organization_ui',reason='Apple HostCatalog shelf() exposes book paging; reviewed HostViews has book list/search and no shelf-tree editor. Product organization APIs do not prove Apple exposed editing.',files=['examples/apple/HostCatalog.swift','examples/apple/HostViews.swift'],anchors=['func shelf(query:','TextField("搜索书名或作者"']),
'R09':dict(classification='catalog_module_not_host_organization_ui',reason='Apple catalog/book list is present, but no tag editor/filter host route established in reviewed HostViews. Shared product grouping does not grant Apple UI.',files=['examples/apple/HostCatalog.swift','examples/apple/HostViews.swift'],anchors=['func shelf(query:','TextField("搜索书名或作者"']),
'R10':dict(classification='catalog_module_not_host_organization_ui',reason='Apple book paging is present, but no series order editor host route established in reviewed HostViews. Shared series module is separate.',files=['examples/apple/HostCatalog.swift','examples/apple/HostViews.swift'],anchors=['func shelf(query:','TextField("搜索书名或作者"']),
'R02':dict(classification='provider_bridge_not_established',reason='Windows cloud dialog is WebDAV-backed, not a system cloud-provider proof. GTK file chooser obtains a local filename; mounted/third-party cloud availability is external and not equivalent to a dedicated Provider integration.',files=['apps/reader/desktop/windows_import_organize_ui.inc','examples/linux/reader.c'],anchors=['WINIO_CLOUD','gtk_file_chooser_get_filename'])}
SEARCH_SCOPES={'Windows':['examples/reader.c','apps/reader/desktop/windows_compact_ui.inc'],'Linux':['examples/linux/reader.c'],'Android':['examples/android/app/src/main/java/org/exreader/host/MainActivity.java'],'Apple':['examples/apple/HostViews.swift','examples/apple/HostCatalog.swift','examples/apple/ReaderApp.swift']}
SEARCH_TERMS={'R24':['reader_ld_'],'R05':['folder_open','ACTION_OPEN_DOCUMENT_TREE','allowedContentTypes: [.folder]'],'R06':['WM_DROPFILES','DragAcceptFiles','onDrop','setOnDragListener'],'R08':['Collections','series','subShelf'],'R09':['Collections','tags','标签'],'R10':['Collections','series','系列']}
