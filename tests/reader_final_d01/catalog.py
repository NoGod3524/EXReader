"""Hand-reviewed source registry; generation and validation run only in Actions."""
BASE='0889f7d1e9a537c6c1b05456547e016b26e1cd85'
SDK='edddc463c06ed5731195cdb8f06b2df6dff7699e'
PLATFORMS=('Windows','Linux','macOS','Android','iPhone','iPad')
# Stable requirements deliberately distinguish import transports and organization entities.
REQUIREMENTS=[
 ('R01','本地系统选择器','extras/sideload'),('R02','第三方云盘文件提供者','apps/reader/cloud-import'),
 ('R03','WebDAV来源/账号','apps/reader/sync'),('R04','电脑传书/实体线缆','extras/sideload'),
 ('R05','文件夹批量导入','apps/reader/batch-import'),('R06','拖放导入','extras/sideload'),
 ('R07','书架','apps/reader/store'),('R08','子书架','apps/reader/bulk-organization'),
 ('R09','分类标签','apps/reader/bulk-organization'),('R10','系列顺序','apps/reader/bulk-organization'),
 ('R11','实际阅读翻页','src'),('R12','书内搜索','apps/reader/search'),
 ('R13','目录/按页入口','apps/reader/navigation'),('R14','阅读进度','apps/reader/reading-state'),
 ('R15','书签/阅读记录','apps/reader/reading-state'),('R16','标注编辑','apps/reader/annotation-view'),
 ('R17','阅读设置','apps/reader/preferences'),('R18','离线已下载原件','apps/reader/local-downloads'),
 ('R19','同步冲突不覆盖','apps/reader/revisions'),('R20','重开/中断恢复','apps/reader/session'),
 ('R21','取消导入','extras/sideload'),('R22','重复/损坏文件','extras/sideload'),
 ('R23','账号不可用','apps/reader/account-profiles'),('R24','移除本机下载/清理测试资料','apps/reader/local-downloads')]
W='apps/reader/desktop/windows_compact_ui.inc'
L='examples/linux/reader.c'
A='examples/android/app/src/main/java/org/exreader/host/MainActivity.java'
S='examples/apple/HostViews.swift'
# file, literal source anchor, visible label, UI route, handler (source token), data owner
ENTRIES={
 'Windows': {
 'R01':(W,'GetOpenFileNameW','导入书籍…','书库 > 导入书籍… / Ctrl+O','compact_import','host owner → SDK原件 + 产品映射'),
 'R02':(W,'IDC_CLOUD_IMPORT','从云盘导入…','书库 > 从云盘导入…','IDC_CLOUD_IMPORT','winio / 产品云盘导入；不代表系统云盘提供者'),
 'R03':(W,'IDC_ACCOUNT_BUTTON','同步账号…','书库 > 同步账号…','IDC_ACCOUNT_BUTTON','account worker / 凭据平台存储、产品修订'),
 'R07':(W,'IDC_COMPACT_SHELF','书架','视图 > 书架 / Alt+←','compact_switch','product shelf / reader-catalog.db'),
 'R11':(W,'IDC_NEXT','下一页','阅读 > 下一页','IDC_NEXT','SDK host owner / 当前帧'),
 'R12':(W,'IDC_INBOOK','书内搜索…','阅读 > 书内搜索…','IDC_INBOOK','SDK owner / 搜索游标'),
 'R13':(W,'IDC_DIRECTORY','目录…','阅读 > 目录…','IDC_DIRECTORY','SDK owner / 目录锚点'),
 'R15':(W,'IDC_RECORDS','书签与阅读记录…','阅读 > 书签与阅读记录…','IDC_RECORDS','reading records owner / 产品修订 + SDK定位'),
 'R16':(W,'IDC_ADD_NOTE','标注编辑…','阅读 > 标注编辑…','IDC_ADD_NOTE','SDK owner / 标注 + 产品记录'),
 'R21':(W,'IDC_CANCEL','取消当前任务','视图 > 取消当前任务','IDC_CANCEL','host job cancellation / 仅本次临时资料')},
 'Linux':{
 'R01':(L,'"Import file…"','Import file…','Import sources ▾ > Import file…','G_CALLBACK(action)','reader worker / SDK + 产品映射'),
 'R03':(L,'G_CALLBACK(accounts_open)','Account / Sync…','More > Account / Sync…','accounts_open','account worker / 安全存储及产品库'),
 'R05':(L,'G_CALLBACK(folder_open)','Import folder…','Import sources ▾ > Import folder…','folder_open','batch import worker / SDK + 产品库'),
 'R06':(L,'file_input_attach(shelf_scroll)','无独立中文标签','拖放至书架滚动区','file_input_attach','file input staging → worker'),
 'R07':(L,'"Bookshelf"','Bookshelf','Shelf F2','shelf','product catalog + SDK映射'),
 'R08':(L,'G_CALLBACK(collections_open)','Collections…','More > Collections…（子书架）','collections_open','collections worker / 产品库'),
 'R09':(L,'G_CALLBACK(collections_open)','Collections…','More > Collections…（标签）','collections_open','collections worker / 产品库'),
 'R10':(L,'G_CALLBACK(collections_open)','Collections…','More > Collections…（系列）','collections_open','collections worker / 产品库'),
 'R11':(L,'"Next F4"','Next F4','Next F4 / F4','G_CALLBACK(action)','reader worker / SDK当前帧'),
 'R12':(L,'G_CALLBACK(inbook_open)','Search within book…','More > Search within book…','inbook_open','SDK owner / 搜索游标'),
 'R13':(L,'G_CALLBACK(directory_open)','Directory / page entries…','More > Directory / page entries…','directory_open','SDK owner / 目录锚点'),
 'R15':(L,'"Reading records…"','Reading records…','Reading records…','reading_records_button','records worker / 产品记录'),
 'R16':(L,'"Add note F8"','Add note F8','Text F7 > Add note F8','G_CALLBACK(action)','SDK owner / 标注'),
 'R17':(L,'G_CALLBACK(preferences_open)','Reading settings…','More > Reading settings…','preferences_open','preferences worker / 设置文件')},
 'Android':{
 'R01':(A,'else startImport();','Import','书架 > Import','startImport','ImportController staging → host worker / SDK + reader-catalog.db'),
 'R03':(A,'else syncPanel.show();','同步','More > 同步','syncPanel.show','sync worker / Keystore、产品库'),
 'R07':(A,'loadShelf(false);','Refresh','书架 > Refresh','loadShelf','native owner / reader-catalog.db'),
 'R08':(A,'organizationPanel.show(0)','Organize','More > Organize（子书架）','organizationPanel.show','organization worker / 产品库'),
 'R09':(A,'organizationPanel.show(0)','Organize','More > Organize（标签）','organizationPanel.show','organization worker / 产品库'),
 'R10':(A,'organizationPanel.show(0)','Organize','More > Organize（系列）','organizationPanel.show','organization worker / 产品库'),
 'R11':(A,'changeFont(1)','字号按钮','打开已下载书 > 阅读页','changeFont','SDK host worker / 当前帧；翻页另需实测'),
 'R12':(A,'searchPanel.show(currentBook.id)','书内搜索','阅读更多操作 > 书内搜索','searchPanel.show','single SDK owner / 搜索游标'),
 'R13':(A,'navigationPanel.show(currentBook.id)','目录 / 按页入口','阅读更多操作 > 目录 / 按页入口','navigationPanel.show','SDK owner / 目录锚点'),
 'R15':(A,'readingPanel.show(currentBook.id','阅读记录','阅读更多操作 > 阅读记录','readingPanel.show','reading owner / 产品记录与SDK'),
 'R16':(A,'annotateSelection()','标注按钮（英文原UI）','选择文本 > 标注','annotateSelection','SDK host worker / 标注'),
 'R17':(A,'preferencesPanel.show()','阅读设置','阅读更多操作 > 阅读设置','preferencesPanel.show','preferences host worker / 设置'),
 'R21':(A,'imports.cancelStaging()','Cancel import','复制期间 > Cancel import','imports.cancelStaging','ImportController / 本次staging')},
 'Apple':{
 'R01':(S,'.fileImporter(isPresented:','打开文件','书架 > 打开文件','model.importFile','HostReaderModel owner / SDK + reader-catalog.db'),
 'R07':(S,'model.openBook(book)','书名（动态）','书架 > 书名','model.openBook','HostCatalog owner / reader-catalog.db + SDK'),
 'R11':(S,'model.turn(1)','下一页','阅读 > 下一页','model.turn','HostReaderModel owner / SDK当前帧'),
 'R12':(S,'model.prepareSearch()','查找','阅读 > 查找','model.prepareSearch','HostSearch owner / SDK游标'),
 'R13':(S,'model.prepareNavigation()','目录','阅读 > 目录','model.prepareNavigation','HostNavigation owner / SDK锚点'),
 'R16':(S,'annotateSelection()','标注所选','阅读 > 选文 > 标注所选','annotateSelection','HostReaderModel owner / SDK标注'),
 'R17':(S,'model.changeFont(2)','增大字号','阅读 > A+','model.changeFont','HostReaderModel / 阅读设置；不代表完整设置面板'),
 'R21':(S,'model.cancelWork()','取消','处理中 > 取消','model.cancelWork','HostReaderModel owner / 本次工作')}
}
EVIDENCE=[
 dict(id='E-WIN',source='eab342ef456be4a8a1811e5249e3c217d906ce8a',delivery='f355525b74ae261db536c56200e46643919ef323',run=40201283788,platforms=['Windows'],scope='独立compact ON + 原OFF回归；非默认完整产品',environment='Windows Actions native UI'),
 dict(id='E-GTK',source='57203a52aee439be5194ee0a4b13563a975e8daf',delivery='9fc407a5cce5a0bfe644a60bd8dc29f84dea6d0e',run=40206458217,platforms=['Linux'],scope='独立compact UI；非共同raw3',environment='Linux Actions GTK/Xvfb'),
 dict(id='E-ANDROID',source='4a04a9cc74dde67f755c87e87b278d63a254a3ac',delivery='caa84411ae79c866c28cf982243b6cb80b4bbe49',run=40207467982,platforms=['Android'],scope='实际raw3候选；非真机六平台',environment='Android emulator'),
 dict(id='E-MAC',source='15dab6b2270dc296ed6239db67ced2e22d255e65',delivery='44eabdc86b3b84d986f81dbaf8cee92b1829cea8',run=40196978163,platforms=['macOS'],scope='实际raw3 Mac候选；非共同双向',environment='macOS Actions'),
 dict(id='E-APPLE-FAILED',source='72c6bbdd14ebf3be453fa7f0da81119d52675eb5',delivery='72c6bbdd14ebf3be453fa7f0da81119d52675eb5',run=40203714083,platforms=['iPhone','iPad'],scope='整轮失败；不得借iPad单叶授予',environment='Apple simulators',retained_failure=True),
 dict(id='E-RECEIVE',source='5062d5cd570eb9be9449e790895b5430d344d11d',delivery='cd6fbe2e4f86c8ebd564d06518427c2642d045f6',run=40210925809,platforms=['Android','macOS'],scope='Android→Mac单向接收；非共同源码双向',environment='mixed candidate producers')]
# Source-traced record entry is distinct from exercising FOUND navigation.
ENTRIES['Apple']['R15']=(S,'model.prepareReadingRecords()','阅读记录','阅读 > 阅读记录','model.prepareReadingRecords','HostReadingRecords owner / 产品修订 + SDK resolve')
ENTRIES['Linux']['R15']=(L,'G_CALLBACK(reading_records_open)','Reading records…','Reading records… / Ctrl+Shift+R','reading_records_open','records worker / 产品记录')
