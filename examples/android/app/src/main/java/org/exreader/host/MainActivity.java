// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ContentResolver;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.util.Log;
import android.view.View;
import android.view.Gravity;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.FrameLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import org.exreader.EXReader;
import org.exreader.importentry.ImportEntry;
import org.exreader.importentry.ReadyRequest;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Single-activity Android host. All SDK access runs on one worker thread; the UI
 * only receives immutable page snapshots and never touches a native handle.
 */
public final class MainActivity extends Activity implements ReaderView.Listener,SyncController.Host,SearchPanel.Host,NavigationPanel.Host,ReadingPanel.Host,PreferencesPanel.Host {
    private static final String TAG = "EXRHost";
    private static final Object IMPORT_LOCK = new Object();
    private static final Object PROGRESS_LOCK = new Object();
    private static final Object PREFERENCES_LOCK = new Object();
    private static final AtomicLong OWNER_EPOCH = new AtomicLong();
    private static final int REQUEST_IMPORT = 1001;
    private static final long MAX_INPUT_BYTES = 32L * 1024 * 1024;
    private static final String PREFS = "host";
    private static final String DOWNLOADS_URI =
            "content://com.android.externalstorage.documents/document/primary%3ADownload";

    private static byte[] FONT;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private ExecutorService worker;
    private BookStore store;
    private ImportController imports;
    private OrganizationPanel organizationPanel;
    private SyncPanel syncPanel;
    private SearchPanel searchPanel;
    private NativeSearch search;
    private NavigationPanel navigationPanel;
    private NativeNavigation navigation;
    private ReadingPanel readingPanel;
    private PreferencesPanel preferencesPanel;
    private volatile ReadingPreferences readingPreferences;
    private String preferencesLoadError;
    private ReadingRequests readingRequests;
    private ReadingHistory readingHistory;
    private PageSnapshot readingFrame;
    private Selection readingSelection;
    private SharedPreferences prefs;

    private LinearLayout shelfPanel;
    private LinearLayout readerPanel;
    private LinearLayout notesPanel;
    private LinearLayout selectionBar;
    private LinearLayout loadingOverlay;
    private ListView bookList;
    private ListView noteList;
    private TextView statusText;
    private TextView readerStatus;
    private TextView sdkLabel;
    private TextView bookTitle;
    private TextView pageLabel;
    private TextView fontLabel;
    private TextView zoomLabel;
    private TextView selectionStatus;
    private TextView notesEmpty;
    private TextView loadingText;
    private Button importButton;
    private Button refreshButton;
    private Button rebuildView;
    private Button backButton;
    private Button fontDown;
    private Button fontUp;
    private Button zoomDown;
    private Button zoomUp;
    private Button selectButton;
    private Button notesButton;
    private Button copyButton;
    private Button annotateButton;
    private Button selectionCancel;
    private Button notesClose;
    private Button cancelButton;
    private ReaderView readerView;

    private CatalogShelf catalogShelf;
    private ShelfWindowMetrics shelfMetrics;
    private long activityStartedNs;
    private EditText shelfSearch;
    private ArrayAdapter<String> noteAdapter;
    private List<?> shownNotes = new ArrayList<>();
    private final List<String> noteRows = new ArrayList<>();

    private NativeLibrary.Book currentBook;
    private ReflowSession reflow;
    private FixedSession fixed;
    private PageSnapshot current;
    private volatile long generation;
    private boolean pageBusy;
    private volatile boolean destroyed;
    private int operation;
    private HostTask activeTask;
    private long sessionBookId; // Worker-owned identity; never inferred from a UI field.
    private long ownerEpoch;
    private long shownNotesBookId;
    private long shownNotesGeneration;
    private PageSnapshot pendingFrame;

    private long bookId;
    private float fontSize = 24f;
    private float zoom = 1f;

    private boolean restoreReader;
    private long restoreBook;
    private long restoreOffset = -1;
    private int restorePage = -1;

    private long pendingStart;
    private long pendingEnd;
    private int pendingPage;
    private boolean pendingFixed;
    private String pendingSelected = "";

    @Override protected void onCreate(Bundle savedInstanceState) {
        activityStartedNs=android.os.SystemClock.elapsedRealtimeNanos();
        super.onCreate(savedInstanceState);
        ownerEpoch = OWNER_EPOCH.incrementAndGet();
        prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        fontSize = prefs.getFloat("font", 24f);
        zoom = prefs.getFloat("zoom", 1f);
        if (savedInstanceState != null) {
            restoreReader = savedInstanceState.getBoolean("reader", false);
            restoreBook = savedInstanceState.getLong("bookId", 0);
            restoreOffset = savedInstanceState.getLong("offset", -1);
            restorePage = savedInstanceState.getInt("page", -1);
            fontSize = savedInstanceState.getFloat("font", fontSize);
            zoom = savedInstanceState.getFloat("zoom", zoom);
        } else {
            restoreReader = prefs.getBoolean("lastReader", false);
            restoreBook = prefs.getLong("lastBook", 0);
        }

        setContentView(R.layout.activity_main);
        bindViews();
        shelfMetrics=ShelfWindowMetrics.start(this,activityStartedNs);
        if(shelfMetrics!=null)catalogShelf.observeFirstInteractive(activityStartedNs);
        wireActions();
        readerView.setListener(this);

        worker = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "exr-host-worker");
            thread.setDaemon(true);
            return thread;
        });
        imports = ImportController.get(this);
        imports.attach(this);
        if (savedInstanceState == null) routeImport(getIntent());

        worker.execute(() -> {
            try {
                if(BuildConfig.READER_PREFERENCES){
                    ReadingPreferences loaded;
                    synchronized(PREFERENCES_LOCK){
                        File file=preferencesFile();HostTask task=new HostTask(()->destroyed||ownerEpoch!=OWNER_EPOCH.get());
                        if(!file.getParentFile().isDirectory()&&!file.getParentFile().mkdirs())throw new IOException("Cannot create settings directory");
                        try{loaded=file.exists()?NativePreferences.load(file.getPath(),task):NativePreferences.importLegacy(prefs.getFloat("font",24f),Math.round(prefs.getFloat("zoom",1f)*100),(prefs.contains("font")?1:0)|(prefs.contains("zoom")?2:0));}
                        catch(RuntimeException error){loaded=NativePreferences.defaults();preferencesLoadError=message(error);}
                    }
                    readingPreferences=loaded;final ReadingPreferences restored=loaded;
                    postUi(()->{fontSize=restored.font;zoom=restored.zoom/100f;readerView.setTurnPreferences(restored.direction,restored.input);});
                }
                // A previous Activity may still be compensating its unpublished insert.
                synchronized (IMPORT_LOCK) {
                    cleanImportTemporaries();
                    store = new BookStore(getApplicationContext(), new File(getFilesDir(), "library.db"));
                }
                if (store.metadataRepairPending()) postStatus("Metadata repair pending; originals retained");
            } catch (Throwable error) {
                postStatus("Library error: " + message(error));
                return;
            }
            postUi(() -> { updateSdkLabel(); imports.pump(); });
            loadShelf(true);
        });
    }

    private void bindViews() {
        shelfPanel = findViewById(R.id.shelf_panel);
        readerPanel = findViewById(R.id.reader_panel);
        notesPanel = findViewById(R.id.notes_panel);
        selectionBar = findViewById(R.id.selection_bar);
        loadingOverlay = findViewById(R.id.loading_overlay);
        bookList = findViewById(R.id.book_list);
        noteList = findViewById(R.id.note_list);
        statusText = findViewById(R.id.status_text);
        readerStatus = findViewById(R.id.reader_status);
        sdkLabel = findViewById(R.id.sdk_label);
        bookTitle = findViewById(R.id.book_title);
        pageLabel = findViewById(R.id.page_label);
        fontLabel = findViewById(R.id.font_label);
        zoomLabel = findViewById(R.id.zoom_label);
        selectionStatus = findViewById(R.id.selection_status);
        notesEmpty = findViewById(R.id.notes_empty);
        loadingText = findViewById(R.id.loading_text);
        importButton = findViewById(R.id.import_button);
        refreshButton = findViewById(R.id.refresh_button);
        rebuildView = findViewById(R.id.rebuild_view);
        backButton = findViewById(R.id.back_button);
        fontDown = findViewById(R.id.font_down);
        fontUp = findViewById(R.id.font_up);
        zoomDown = findViewById(R.id.zoom_down);
        zoomUp = findViewById(R.id.zoom_up);
        selectButton = findViewById(R.id.select_button);
        notesButton = findViewById(R.id.notes_button);
        copyButton = findViewById(R.id.copy_button);
        annotateButton = findViewById(R.id.annotate_button);
        selectionCancel = findViewById(R.id.selection_cancel);
        notesClose = findViewById(R.id.notes_close);
        cancelButton = findViewById(R.id.cancel_button);
        readerView = findViewById(R.id.reader_view);

        shelfSearch=findViewById(R.id.shelf_search);
        ShelfStatusView shelfSummary=findViewById(R.id.shelf_summary);
        catalogShelf=new CatalogShelf(this,bookList,shelfSearch,shelfSummary,prefs,
                action->{ if (worker!=null) worker.execute(action); },
                (query,anchor,before,inclusive,cancellation)->{
                    if (store==null) throw new IllegalStateException("Library is still opening");
                    return store.shelfPage(query,anchor,before,inclusive,cancellation);
                },error->setStatus("Shelf error: "+message(error)));
        shelfSummary.bind(catalogShelf);
        noteAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, noteRows);
        noteList.setAdapter(noteAdapter);
        statusText.setContentDescription("Status");
        organizationPanel=new OrganizationPanel(this,action->{if(worker!=null)worker.execute(action);},()->store,()->catalogShelf.load());
        if(BuildConfig.READER_SYNC)syncPanel=new SyncPanel(this,this);
        if(BuildConfig.READER_SEARCH)searchPanel=new SearchPanel(this,this);
        if(BuildConfig.READER_NAVIGATION)navigationPanel=new NavigationPanel(this,this);
        if(BuildConfig.READER_READING)readingPanel=new ReadingPanel(this,this);
        if(BuildConfig.READER_PREFERENCES)preferencesPanel=new PreferencesPanel(this,this);
    }

    private void wireActions() {
        findViewById(R.id.more_button).setOnClickListener(view->new android.app.AlertDialog.Builder(this)
                .setTitle("More").setItems(BuildConfig.READER_SYNC?new String[]{"Organize","同步"}:new String[]{"Organize"},(dialog,which)->{if(which==0)organizationPanel.show(0);else syncPanel.show();}).show());
        bookList.setOnItemLongClickListener((parent,view,position,id)->{
            if(operation!=0||pageBusy||id<=0)return true;
            new android.app.AlertDialog.Builder(this).setItems(new String[]{"Organize book"},(dialog,which)->organizationPanel.show(id)).show();return true;
        });
        importButton.setOnClickListener(view -> {
            if(imports.isCopying()){imports.cancelStaging();setStatus(imports.isCopying()?"Canceling import...":"Import canceled");}
            else startImport();
        });
        refreshButton.setOnClickListener(view -> {
            loadShelf(false);
            setStatus("Shelf refreshed");
            imports.retry();
        });
        rebuildView.setOnClickListener(view -> {
            saveInstancePrefs();recreate();
        });
        View readerMore=findViewById(R.id.reader_more);readerMore.setVisibility(BuildConfig.READER_SEARCH||BuildConfig.READER_NAVIGATION||BuildConfig.READER_READING||BuildConfig.READER_PREFERENCES?View.VISIBLE:View.GONE);
        if((BuildConfig.READER_SEARCH||BuildConfig.READER_NAVIGATION)&&!BuildConfig.DEBUG)rebuildView.setVisibility(View.GONE);
        readerMore.setOnClickListener(view->{ArrayList<String> actions=new ArrayList<>();if(BuildConfig.READER_PREFERENCES)actions.add("阅读设置");if(BuildConfig.READER_SEARCH)actions.add("书内搜索");if(BuildConfig.READER_NAVIGATION)actions.add("目录 / 按页入口");if(BuildConfig.READER_READING)actions.add("阅读记录");new AlertDialog.Builder(this).setTitle("阅读更多操作").setItems(actions.toArray(new String[0]),(dialog,which)->{
            if(currentBook==null||current==null||operation!=0||pageBusy){setStatus("请先完成当前阅读操作");return;}
            String action=actions.get(which);if(action.equals("阅读设置"))preferencesPanel.show();else if(action.equals("书内搜索"))searchPanel.show(currentBook.id);else if(action.equals("目录 / 按页入口"))navigationPanel.show(currentBook.id);else{readingPanel.close();readingFrame=current;readingSelection=readerView.getSelection();readingPanel.show(currentBook.id,readingSelection!=null&&readingSelection.end>readingSelection.start);}
        }).show();});
        backButton.setOnClickListener(view -> leaveReader());
        fontDown.setOnClickListener(view -> changeFont(-1));
        fontUp.setOnClickListener(view -> changeFont(1));
        zoomDown.setOnClickListener(view -> changeZoom(-1));
        zoomUp.setOnClickListener(view -> changeZoom(1));
        selectButton.setOnClickListener(view -> {
            boolean next = !readerView.isSelectMode();
            readerView.setSelectMode(next);
        });
        notesButton.setOnClickListener(view -> showNotes());
        notesClose.setOnClickListener(view -> hideNotes());
        copyButton.setOnClickListener(view -> copySelection());
        annotateButton.setOnClickListener(view -> annotateSelection());
        selectionCancel.setOnClickListener(view -> readerView.setSelectMode(false));
        cancelButton.setOnClickListener(view -> {
            imports.cancelStaging();
            if (activeTask != null) activeTask.cancel();
            loadingText.setText("Canceling operation...");
        });
        bookList.setOnItemClickListener((parent, view, position, id) -> {
            if (operation != 0 || pageBusy) return;
            if (position < 0 || position >= catalogShelf.getCount() || id<=0) return;
            catalogShelf.save();
            shelfSearch.clearFocus();
            ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE))
                    .hideSoftInputFromWindow(shelfSearch.getWindowToken(),0);
            if (currentBook != null && currentBook.id == id && current != null) {
                showReader(currentBook);
                return;
            }
            openBook(id, -1, -1);
        });
        noteList.setOnItemClickListener((parent, view, position, id) -> {
            if (operation != 0 || pageBusy || currentBook == null ||
                    shownNotesBookId != currentBook.id || shownNotesGeneration != generation) return;
            if (position < 0 || position >= shownNotes.size()) return;
            Object note = shownNotes.get(position);
            hideNotes();
            navigateTo(note);
        });
        noteList.setOnItemLongClickListener((parent, view, position, id) -> {
            if (operation != 0 || pageBusy || currentBook == null ||
                    shownNotesBookId != currentBook.id || shownNotesGeneration != generation) return true;
            if (position < 0 || position >= shownNotes.size()) return true;
            Object note = shownNotes.get(position);
            pendingFrame = current;
            if (note instanceof NativeLibrary.FixedNote) {
                NativeLibrary.FixedNote fixedNote = (NativeLibrary.FixedNote) note;
                pendingFixed = true;
                pendingPage = (int) fixedNote.page;
                pendingStart = fixedNote.start;
                pendingEnd = fixedNote.end;
                pendingSelected = fixedNote.selected;
                showNoteDialog(fixedNote.id, fixedNote.comment, false);
            } else if (note instanceof NativeLibrary.Note) {
                NativeLibrary.Note reflowNote = (NativeLibrary.Note) note;
                pendingFixed = false;
                pendingStart = reflowNote.start;
                pendingEnd = reflowNote.end;
                pendingSelected = reflowNote.selected;
                showNoteDialog(reflowNote.id, reflowNote.comment, false);
            }
            return true;
        });
    }

    private void loadShelf(boolean maybeOpen) {
        if (worker == null) return;
        postUi(() -> {
            if (maybeOpen) {
                long target = restoreBook;
                if (target <= 0) target = prefs.getLong("lastBook", 0);
                boolean reader = restoreReader || prefs.getBoolean("lastReader", false);
                if (reader && target > 0) {
                    final long openId = target;
                    final long openOffset = restoreOffset;
                    final int openPage = restorePage;
                    openBook(openId, openOffset, openPage);
                } else {
                    showShelf(false);
                }
            } else catalogShelf.load();
        });
    }

    private HostTask beginTask(int kind) {
        if(searchPanel!=null)searchPanel.close();
        if(navigationPanel!=null)navigationPanel.close();
        if(readingPanel!=null)readingPanel.close();
        if (activeTask != null) activeTask.cancel();
        final long gen = ++generation;
        HostTask task = new HostTask(() -> destroyed || generation != gen);
        activeTask = task;
        operation = kind;
        pageBusy = true;
        readerView.setSelectMode(false);
        readerView.clearSelection();
        setActionsEnabled(false);
        return task;
    }

    private void setActionsEnabled(boolean enabled) {
        findViewById(R.id.more_button).setEnabled(enabled);
        for (View view : new View[]{importButton, refreshButton, bookList, shelfSearch, fontDown, fontUp,
                zoomDown, zoomUp, selectButton, notesButton, copyButton, annotateButton, readerView}) {
            view.setEnabled(enabled);
        }
    }

    private void finishTask(long gen) {
        if (gen != generation) return;
        activeTask = null;
        operation = 0;
        pageBusy = false;
        hideLoading();
        setActionsEnabled(true);
        ui.post(() -> { if (!destroyed && imports != null) imports.pump(); });
    }

    private void taskFailed(long gen, String prefix, Throwable error) {
        postUi(() -> {
            if (gen != generation) return;
            finishTask(gen);
            setStatus(error instanceof HostTask.Cancelled ? "Operation canceled" : prefix + message(error));
        });
    }

    // One debug-only phase gate is used by cloud UI tests. It observes actual
    // file/SDK work; ordinary launches never wait here.
    private void reviewGate(String phase, HostTask task) throws Exception {
        if (!BuildConfig.DEBUG || !getIntent().getBooleanExtra("exr_review", false) ||
                !phase.equals(getIntent().getStringExtra("review_pause"))) return;
        File release = new File(getFilesDir(), "review-release");
        postUi(() -> loadingText.setText("Review " + phase));
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(
                "progress-before-write".equals(phase) ? 60 : 20);
        while (!release.isFile()) {
            task.check();
            if (System.nanoTime() > deadline) throw new IOException("Cloud review phase was not released");
            Thread.sleep(10);
        }
        if (!release.delete()) throw new IOException("Cannot remove review release marker");
    }

    private void openBook(long id, long offset, int page) {
        if (worker == null || operation != 0 || pageBusy) return;
        if (store == null) {
            setStatus("Library is still opening");
            return;
        }
        CatalogStore.ShelfBook shown=catalogShelf.cachedBook(id);
        final String displayTitle=shown==null ? "book" : shown.title;
        final HostTask task = beginTask(2);
        final long gen = generation;
        final float requestedFont = fontSize, requestedZoom = zoom;
        final ReadingPreferences requestedAppearance=readingPreferences;
        showLoading("Opening " + displayTitle + "...", true);
        final long requestedOffset = offset;
        final int requestedPage = page;
        worker.execute(() -> {
            ReflowSession candidateReflow = null;
            FixedSession candidateFixed = null;
            PageLoad load = null;
            boolean accepted = false;
            String notice = null;
            String resolvedTitle = displayTitle;
            try {
                task.check();
                CatalogStore.ShelfBook local=store.localShelfBook(id);
                if (local==null) throw new IOException("Book is not available on this device");
                resolvedTitle=local.title;
                final String loadingTitle=local.title;
                postUi(()->{if(gen==generation && activeTask==task)loadingText.setText("Opening "+loadingTitle+"...");});
                // The frozen SDK exposes metadata as an enumeration; keep that read on its owner,
                // only for the chosen book, instead of rebuilding the entire shelf on every refresh.
                final NativeLibrary.Book target=store.find(id);
                if (target==null) throw new IOException("Book is missing from the SDK library");
                String path = prefs.getString("path_" + target.id, null);
                boolean bounded = target.format==NativeLibrary.FORMAT_EPUB && store.bounded(target.id);
                Log.i(TAG,"storage mode book="+target.id+" bounded="+bounded);
                if (!bounded && (path == null || !new File(path).isFile())) {
                    throw new IOException("The app-owned book copy is missing");
                }
                if(BuildConfig.READER_READING){
                    String expected=local.key.bookKey.substring(local.key.bookKey.indexOf(':')+1);
                    BookStore.VerifiedSource verified=store.verifySource(target.id,expected,local.sourceBytes,task);
                    if(!verified.key.equals(local.key.bookKey))throw new IOException("Displayed original identity differs");
                    if(!bounded&&(new File(path).length()!=verified.bytes||!BookStore.syncFileHash(new File(path),task).equals(verified.sha256)))throw new IOException("Displayed copy differs from the verified original");
                }
                if (target.fixed()) {
                    candidateFixed = new FixedSession(target.id,path,fontBytes(),target.format,task);
                    if(candidateFixed.cbz()&&!local.key.bookKey.equals(candidateFixed.sourceKey()))throw new IOException("CBZ renderer original identity differs");
                    int requested = requestedPage >= 0 ? requestedPage : (int) Math.max(0, target.position);
                    load = candidateFixed.load(requested, requestedZoom, task);
                } else if(bounded) {
                    candidateReflow=requestedAppearance==null?new ReflowSession(store,target.id,fontBytes(),requestedFont):new ReflowSession(store,target.id,fontBytes(),requestedAppearance);
                    int display=requestedPage>=0?requestedPage:prefs.getInt("display_"+target.id,0);
                    load=candidateReflow.restore(display,task);
                    notice=load.snapshot.restoreNotice;
                } else {
                    candidateReflow = requestedAppearance==null?new ReflowSession(target.id,path,fontBytes(),requestedFont):new ReflowSession(target.id,path,fontBytes(),requestedAppearance);
                    long savedOffset = requestedOffset;
                    int state = -1;
                    if (savedOffset < 0) {
                        long[] progress = store.progress(target.id);
                        if (progress != null && progress.length >= 2) {
                            state = (int) progress[0];
                            savedOffset = progress[1];
                        }
                    }
                    long seek = savedOffset;
                    if (seek < 0) seek = target.position;
                    if (seek < 0) seek = 0;
                    boolean exact = state == 1 || (state == 3 && seek == 0);
                    if (requestedOffset < 0 && state >= 0 && !exact) {
                        notice = "Saved position is not exact (state " + state
                                + "); opened at stored offset " + seek + ".";
                    }
                    load = candidateReflow.seek(seek, task);
                }
                if (load == null) throw new IllegalStateException("The book has no readable pages");
                Log.i(TAG, "handle open book=" + target.id + " mode=" + (target.fixed() ? "fixed" : "reflow"));
                final ReflowSession nextReflow = candidateReflow;
                final FixedSession nextFixed = candidateFixed;
                final PageLoad[] delivery={load};
                try {
                    task.commit(() -> {
                        delivery[0]=persistPage(delivery[0],task);delivery[0].snapshot.sourceKey=local.key.bookKey;delivery[0].accept();
                        closeSessionsLocked(); reflow=nextReflow; fixed=nextFixed; sessionBookId=target.id;
                    });
                } finally { load=delivery[0]; }
                final PageLoad result=load;
                accepted = true;
                final String restored = notice;
                postUi(() -> {
                    if (gen != generation) return;
                    finishTask(gen);
                    currentBook = target;
                    bookId = target.id;
                    prefs.edit().putLong("lastBook", target.id).putBoolean("lastReader", true).apply();
                    showReader(target);
                    setStatus("Opened " + target.title);
                    applyPage(gen, result, restored);
                    refreshNotesCount();
                });
            } catch (Throwable error) {
                taskFailed(gen, "Could not open " + resolvedTitle + ": ", error);
            } finally {
                if (load != null) load.close();
                if (!accepted) {
                    if (candidateReflow != null) candidateReflow.close();
                    if (candidateFixed != null) candidateFixed.close();
                }
            }
        });
    }

    private void applyPage(long gen, PageLoad load, String notice) {
        if (gen != generation) return;
        finishTask(gen);
        current = load.snapshot;
        pageBusy = false;
        readerView.setSelectMode(false);
        readerView.setPage(current);
        selectButton.setText("Select");
        selectionBar.setVisibility(View.GONE);
        selectionStatus.setText("");
        bookTitle.setText(currentBook == null ? "" : currentBook.title);
        pageLabel.setText(pageSummary(load));
        fontLabel.setText("Size " + (int) fontSize);
        describeValue(fontDown,"Decrease font size",fontLabel.getText());
        describeValue(fontUp,"Increase font size",fontLabel.getText());
        zoomLabel.setText(String.format(Locale.US, "Zoom %.2f", zoom));
        describeValue(zoomDown,"Zoom out",zoomLabel.getText());
        describeValue(zoomUp,"Zoom in",zoomLabel.getText());
        boolean isFixed = current.fixed;
        fontDown.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        fontUp.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        fontLabel.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        zoomDown.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        zoomUp.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        zoomLabel.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        if (notice != null || current.restoreNotice!=null) setStatus(notice!=null?notice:current.restoreNotice);
        if(BuildConfig.READER_PREFERENCES&&preferencesLoadError!=null)setStatus("设置未载入，原文件保留："+preferencesLoadError);
        else if(BuildConfig.READER_PREFERENCES&&readingPreferences!=null&&readingPreferences.theme==3&&systemTheme()==2)setStatus("系统为深色；阅读页配色暂不支持，保留原页");
        Log.i(TAG, "metric {\"event\":\"page\",\"book\":" + bookId + ",\"page\":" + (current.index + 1)
                + ",\"fixed\":" + isFixed + ",\"bytes\":" + current.bitmapBytes
                + ",\"ms\":" + load.millis + "}");
    }

    private static void describeValue(View view,String label,CharSequence value){
        if(Build.VERSION.SDK_INT>=30){view.setContentDescription(label);view.setStateDescription(value);}
        else view.setContentDescription(label+". "+value);
    }

    private String pageSummary(PageLoad load) {
        PageSnapshot page = load.snapshot;
        String head = page.fixed
                ? (currentBook != null && currentBook.format == NativeLibrary.FORMAT_CBZ ? "CBZ p." : "PDF p.")
                + (page.index + 1) + "/" + page.pageCount
                : "p." + (page.index + 1);
        return String.format(Locale.US, "%s · %.1f MiB · %d ms",
                head, page.bitmapBytes / (1024.0 * 1024.0), load.millis);
    }

    private void showReader(NativeLibrary.Book book) {
        shelfPanel.setVisibility(View.GONE);
        notesPanel.setVisibility(View.GONE);
        readerPanel.setVisibility(View.VISIBLE);
        bookTitle.setText(book.title);
        prefs.edit().putLong("lastBook", book.id).putBoolean("lastReader", true).apply();
    }

    private void showShelf(boolean closeSessions) {
        if (closeSessions) {
            ++generation;
            pageBusy = false;
            current = null;
            readerView.setPage(null);
            if (worker != null) worker.execute(this::closeSessionsLocked);
        }
        readerPanel.setVisibility(View.GONE);
        notesPanel.setVisibility(View.GONE);
        shelfPanel.setVisibility(View.VISIBLE);
        selectionBar.setVisibility(View.GONE);
        prefs.edit().putBoolean("lastReader", false).apply();
        loadShelf(false);
        if(imports!=null)ui.post(imports::pump);
    }

    private void leaveReader() {
        if (activeTask != null) activeTask.cancel();
        ++generation;
        operation = 0;
        activeTask = null;
        pageBusy = false;
        hideLoading();
        setActionsEnabled(true);
        current = null;
        currentBook = null;
        bookId = 0;
        readerView.setPage(null);
        readerPanel.setVisibility(View.GONE);
        notesPanel.setVisibility(View.GONE);
        shelfPanel.setVisibility(View.VISIBLE);
        selectionBar.setVisibility(View.GONE);
        prefs.edit().putBoolean("lastReader", false).apply();
        if (worker != null) {
            worker.execute(this::closeSessionsLocked);
        }
        loadShelf(false);
    }

    private void turnPage(int delta) {
        if (worker == null || current == null || pageBusy || operation != 0) return;
        final boolean isFixed = current.fixed;
        final float scale = zoom;
        runPage(task -> isFixed ? fixed.load(fixed.index() + delta, scale, task) :
                (delta > 0 ? reflow.next(task) : reflow.previous(task)),
                () -> {}, delta > 0 ? "End of book" : "Start of book");
    }

    private interface PageAction { PageLoad run(HostTask task) throws Exception; }

    private void runPage(PageAction action, Runnable accepted, String empty) {
        if (worker == null || current == null || operation != 0 || pageBusy) return;
        final long owner = current.bookId;
        final String pageSourceKey=current.sourceKey;
        final HostTask task = beginTask(3);
        final long gen = generation;
        showLoading("Loading page...", true);
        worker.execute(() -> {
            PageLoad load = null;
            android.database.sqlite.SQLiteDatabase fault = null;
            try {
                task.check();
                if (sessionBookId != owner) throw new IllegalStateException("The reading book changed");
                reviewGate("page-before-render", task);
                if(BuildConfig.DEBUG && getIntent().hasExtra("review_chapter_budget")) {
                    int budget=getIntent().getIntExtra("review_chapter_budget",8*1024*1024);
                    getIntent().removeExtra("review_chapter_budget");
                    if(reflow!=null) reflow.reviewChapterBudget(budget);
                }
                if(BuildConfig.DEBUG && getIntent().getBooleanExtra("review_external_commit",false)) {
                    getIntent().removeExtra("review_external_commit");
                    try(android.database.sqlite.SQLiteDatabase changed=android.database.sqlite.SQLiteDatabase.openDatabase(
                            new File(getFilesDir(),"library.db").getPath(),null,0)) {
                        changed.execSQL("CREATE TABLE host_review_commit(value INTEGER)");
                        changed.execSQL("DROP TABLE host_review_commit");
                    }
                }
                if (BuildConfig.DEBUG && getIntent().getBooleanExtra("review_fail_progress", false)) {
                    getIntent().removeExtra("review_fail_progress");
                    fault = android.database.sqlite.SQLiteDatabase.openDatabase(
                            new File(getFilesDir(), "library.db").getPath(), null, 0);
                    String table=reflow!=null && reflow.bounded()?"epub_progress":"book_progress";
                    fault.execSQL("CREATE TRIGGER host_review_progress BEFORE INSERT ON "+table+" BEGIN SELECT RAISE(ABORT,'host-review'); END");
                    if(reflow!=null) reflow.refreshSource();
                }
                load = action.run(task);
                if (load == null) {
                    postUi(() -> { if (gen == generation) { finishTask(gen); setStatus(empty); } });
                    return;
                }
                final PageLoad[] delivery={load};
                try { task.commit(() -> { delivery[0]=persistPage(delivery[0],task);delivery[0].snapshot.sourceKey=pageSourceKey;delivery[0].accept(); }); }
                finally { load=delivery[0]; }
                final PageLoad result=load;
                postUi(() -> {
                    if (gen != generation) return;
                    accepted.run();
                    applyPage(gen, result, null);
                });
            } catch (Throwable error) { taskFailed(gen, "Page error: ", error); }
            finally {
                if (fault != null) {
                    try { fault.execSQL("DROP TRIGGER IF EXISTS host_review_progress"); }
                    finally { fault.close(); }
                }
                if (load != null) load.close();
                if(reflow!=null) reflow.reviewChapterBudget(8*1024*1024);
                if(fault!=null && reflow!=null) reflow.refreshSource();
            }
        });
    }

    private void changeFont(int direction) {
        if (worker == null || current == null || current.fixed || pageBusy || operation != 0) return;
        float size = Math.max(BuildConfig.READER_PREFERENCES?4f:18f, Math.min(BuildConfig.READER_PREFERENCES?256f:40f, fontSize + direction * 4f));
        if (size == fontSize) {
            setStatus("Font size limit");
            return;
        }
        if(BuildConfig.READER_PREFERENCES){ReadingPreferences p=readingPreferences;preferencesApply(p.with(size,p.line,p.paragraph,p.margin,p.theme,p.direction,p.input,p.zoom),()->{},error->setStatus(message(error)));return;}
        runPage(task -> reflow.setFontSize(size, task), () -> {
            fontSize = size;
            prefs.edit().putFloat("font", size).apply();
            setStatus("Font size " + (int) size);
        }, "The book has no readable pages");
    }

    private void changeZoom(int direction) {
        if (worker == null || current == null || !current.fixed || pageBusy || operation != 0) return;
        float next = Math.max(BuildConfig.READER_PREFERENCES?.25f:1.0f, Math.min(BuildConfig.READER_PREFERENCES?4.0f:2.0f, zoom + direction * 0.25f));
        if (next == zoom) {
            setStatus("Zoom limit");
            return;
        }
        if(BuildConfig.READER_PREFERENCES){ReadingPreferences p=readingPreferences;preferencesApply(p.with(p.font,p.line,p.paragraph,p.margin,p.theme,p.direction,p.input,Math.round(next*100)),()->{},error->setStatus(message(error)));return;}
        runPage(task -> fixed.load(fixed.index(), next, task), () -> {
            zoom = next;
            prefs.edit().putFloat("zoom", next).apply();
            setStatus(String.format(Locale.US, "Zoom %.2f", zoom));
        }, "The book has no readable pages");
    }

    private PageLoad persistPage(PageLoad request,HostTask task) throws Exception {
        try { saveProgressLocked(request.snapshot,task); return request; }
        catch(RuntimeException error) {
                String detail=error.getMessage();
                if(!request.snapshot.bounded || detail==null || !detail.contains("code 3")) throw error;
                // Another Activity can commit while this candidate waits for the
                // publication lock. Rebuild and resolve its captured point before
                // showing any pixels from the new source. A DB rejection is not retried.
                PageSnapshot previous=request.snapshot; request.close();
                PageLoad rebuilt=previous.boundedOwner.retryFrame(previous,task);
                try { saveProgressLocked(rebuilt.snapshot,task); return rebuilt; }
                catch(Exception|Error retryError) { rebuilt.close(); throw retryError; }
        }
    }

    private void saveProgressLocked(PageSnapshot snapshot, HostTask task) throws Exception {
        if (store == null || snapshot == null || snapshot.bookId <= 0) return;
        Log.i(TAG, "progress attempt {\"owner\":" + ownerEpoch + ",\"book\":" + snapshot.bookId
                + ",\"index\":" + snapshot.index + "}");
        // Only workers take this lock. An old in-flight save finishes before a
        // new Activity can publish progress; a queued stale owner cannot save.
        synchronized (PROGRESS_LOCK) {
            if (destroyed || ownerEpoch != OWNER_EPOCH.get()) throw new HostTask.Cancelled();
            reviewGate("progress-before-write", task);
            if(snapshot.bounded) BoundedEpub.checkSource(snapshot);
            if (snapshot.fixed) {
                store.setPosition(snapshot.bookId, snapshot.index);
            } else if(snapshot.bounded && !snapshot.preserveProgress) {
                BoundedEpub.storeProgress(store.nativeLibrary(),snapshot);
                prefs.edit().putInt("display_"+snapshot.bookId,snapshot.index).apply();
            } else if(!snapshot.bounded) {
                store.saveProgress(snapshot.bookId, snapshot.start);
            }
        }
    }

    private void closeSessionsLocked() {
        closeSearchNative();
        closeDirectoryNative();
        boolean closed = false;
        if (reflow != null) {
            reflow.close();
            reflow = null;
            closed = true;
        }
        if (fixed != null) {
            fixed.close();
            fixed = null;
            closed = true;
        }
        if (closed) Log.i(TAG, "handle close book=" + sessionBookId);
        sessionBookId = 0;
    }

    private void refreshNotesCount() {
        if (worker == null || currentBook == null) return;
        final NativeLibrary.Book book = currentBook;
        final long gen = generation;
        worker.execute(() -> {
            try {
                final int value = book.fixed() ? store.fixedNotes(book.id).size() : store.notes(book.id).size();
                postUi(() -> {
                    if (gen == generation && currentBook != null && currentBook.id == book.id)
                        notesButton.setText("Notes (" + value + ")");
                });
            } catch (Throwable error) {
                postUi(() -> { if (gen == generation) setStatus("Annotation count error: " + message(error)); });
            }
        });
    }

    private void showNotes() {
        if (worker == null || currentBook == null || pageBusy || operation != 0) return;
        final NativeLibrary.Book book = currentBook;
        final long gen = generation;
        worker.execute(() -> {
            try {
                List<String> rows = new ArrayList<>();
                List<?> notes;
                if (book.fixed()) {
                    List<NativeLibrary.FixedNote> fixedNotes = store.fixedNotes(book.id);
                    notes = fixedNotes;
                    for (NativeLibrary.FixedNote note : fixedNotes) {
                        rows.add(note.comment + " — " + ReaderView.clip(note.selected, 60)
                                + " (p." + (note.page + 1) + ")");
                    }
                } else {
                    List<NativeLibrary.Note> reflowNotes = store.notes(book.id);
                    notes = reflowNotes;
                    for (NativeLibrary.Note note : reflowNotes) {
                        rows.add(note.comment + " — " + ReaderView.clip(note.selected, 60));
                    }
                }
                postUi(() -> {
                    if (gen != generation || currentBook == null || currentBook.id != book.id) return;
                    shownNotesBookId = book.id;
                    shownNotesGeneration = gen;
                    showNotesPanel(rows, notes);
                });
            } catch (Throwable error) {
                postUi(() -> {
                    if (gen == generation && currentBook != null && currentBook.id == book.id)
                        setStatus("Annotation list error: " + message(error));
                });
            }
        });
    }

    private void showNotesPanel(List<String> rows, List<?> notes) {
        shownNotes = notes;
        noteRows.clear();
        noteRows.addAll(rows);
        noteAdapter.notifyDataSetChanged();
        notesEmpty.setVisibility(rows.isEmpty() ? View.VISIBLE : View.GONE);
        noteList.setVisibility(rows.isEmpty() ? View.GONE : View.VISIBLE);
        notesPanel.setVisibility(View.VISIBLE);
    }

    private void hideNotes() {
        notesPanel.setVisibility(View.GONE);
    }

    private void navigateTo(Object note) {
        if (current == null || current.bookId != shownNotesBookId || generation != shownNotesGeneration) return;
        final float scale = zoom;
        if (note instanceof NativeLibrary.FixedNote) {
            NativeLibrary.FixedNote value = (NativeLibrary.FixedNote) note;
            if (value.page < 0 || value.start < 0) { setStatus("Annotation range is unresolved"); return; }
            runPage(task -> fixed.load((int) value.page, scale, task),
                    () -> setStatus("Jumped to annotation"), "Annotation page is missing");
        } else {
            NativeLibrary.Note value = (NativeLibrary.Note) note;
            if (value.start < 0) { setStatus("Annotation range is unresolved"); return; }
            runPage(task -> reflow.seek(value, task),
                    () -> setStatus("Jumped to annotation"), "Annotation page is missing");
        }
    }

    private void copySelection() {
        if (pageBusy || operation != 0) return;
        Selection selection = readerView.getSelection();
        if (selection == null || selection.text.isEmpty()) {
            setStatus("No text is selected");
            return;
        }
        ClipboardManager clipboard = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
        if (clipboard != null) {
            clipboard.setPrimaryClip(ClipData.newPlainText("EXReader", selection.text));
        }
        int characters = selection.text.codePointCount(0, selection.text.length());
        setStatus("Copied " + characters + " characters");
        Log.i(TAG, "metric {\"event\":\"copy\",\"chars\":" + characters + "}");
    }

    private void annotateSelection() {
        if (pageBusy || operation != 0 || current == null) return;
        Selection selection = readerView.getSelection();
        if (selection == null || selection.text.isEmpty()) {
            setStatus("Select text first");
            return;
        }
        pendingFixed = current != null && current.fixed;
        pendingStart = selection.start;
        pendingEnd = selection.end;
        pendingPage = selection.pageIndex;
        pendingSelected = selection.text;
        pendingFrame = current;
        showNoteDialog(0, "", true);
    }

    private void showNoteDialog(long noteId, String initial, boolean isNew) {
        EditText input = new EditText(this);
        input.setId(R.id.note_comment);
        input.setHint("Comment");
        input.setText(initial);
        input.setMinLines(2);
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        AlertDialog.Builder builder = new AlertDialog.Builder(this)
                .setTitle(isNew ? "New annotation" : "Edit annotation")
                .setView(input)
                .setPositiveButton("Save", (dialog, which) -> saveNote(noteId, input.getText().toString()))
                .setNeutralButton("Cancel", null);
        if (!isNew) builder.setNegativeButton("Delete", (dialog, which) -> deleteNote(noteId));
        builder.show();
    }

    private void saveNote(long noteId, String raw) {
        final PageSnapshot frame = pendingFrame;
        if (worker == null || frame == null || frame != current || pageBusy || operation != 0) {
            setStatus("The selected page changed; select text again");
            return;
        }
        String comment = raw == null ? "" : raw.trim();
        if (comment.isEmpty()) comment = ReaderView.clip(pendingSelected, 80);
        if (comment.isEmpty()) comment = "(no comment)";
        final String text = comment;
        final boolean isFixed = frame.fixed;
        final long start = pendingStart;
        final long end = pendingEnd;
        final int page = pendingPage;
        final HostTask task = beginTask(4);
        final long gen = generation;
        worker.execute(() -> {
            try {
                task.check();
                if (sessionBookId != frame.bookId) throw new IllegalStateException("The reading book changed");
                task.commit(() -> {
                    if (isFixed) store.saveFixedNote(frame.bookId, noteId, page, start, end, text);
                    else if(frame.bounded) reflow.saveBoundedNote(noteId,start,end,text);
                    else if (noteId > 0) store.updateNoteText(frame.bookId, noteId, text);
                    else store.saveNote(frame.bookId, 0, start, end, text);
                });
                postUi(() -> {
                    if (gen != generation) return;
                    finishTask(gen);
                    setStatus(noteId > 0 ? "Annotation updated" : "Annotation saved");
                    refreshNotesCount();
                    if (notesPanel.getVisibility() == View.VISIBLE) showNotes();
                });
            } catch (Throwable error) {
                taskFailed(gen, "Could not save annotation: ", error);
            }
        });
    }

    private void deleteNote(long noteId) {
        final PageSnapshot frame = pendingFrame;
        if (worker == null || frame == null || frame != current || pageBusy || operation != 0) return;
        final boolean isFixed = frame.fixed;
        final HostTask task = beginTask(4);
        final long gen = generation;
        worker.execute(() -> {
            try {
                task.check();
                if (sessionBookId != frame.bookId) throw new IllegalStateException("The reading book changed");
                task.commit(() -> {
                    if (isFixed) store.removeFixedNote(frame.bookId, noteId);
                    else store.removeNote(frame.bookId, noteId);
                });
                postUi(() -> {
                    if (gen != generation) return;
                    finishTask(gen);
                    setStatus("Annotation deleted");
                    hideNotes();
                    refreshNotesCount();
                });
            } catch (Throwable error) {
                taskFailed(gen, "Could not delete annotation: ", error);
            }
        });
    }

    private void startImport() {
        if (pageBusy || operation != 0) return;
        Intent intent = ImportEntry.pickerIntent(true);
        intent.putExtra(DocumentsContract.EXTRA_INITIAL_URI, Uri.parse(DOWNLOADS_URI));
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try {
            startActivityForResult(intent, REQUEST_IMPORT);
        } catch (ActivityNotFoundException error) {
            setStatus("No system file picker is available");
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_IMPORT) return;
        if(BuildConfig.DEBUG)Log.i(TAG,"system import result request="+requestCode+" result="+resultCode
                +" data="+(data!=null&&data.getData()!=null)+" flags="+(data==null?0:data.getFlags())
                +" clips="+(data==null||data.getClipData()==null?0:data.getClipData().getItemCount()));
        if (resultCode != RESULT_OK || data == null) {
            setStatus("Selection canceled");
            return;
        }
        imports.submit(data);
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (routeImport(intent)) return;
        if (!BuildConfig.DEBUG || !intent.getBooleanExtra("exr_review", false)) return;
        if(intent.hasExtra("review_progress_identity")) {
            String label=intent.getStringExtra("review_progress_identity");
            intent.removeExtra("review_progress_identity");
            if(worker==null || current==null) return;
            final long selected=current.bookId;
            worker.execute(()->{
                try {
                    String identity=BoundedEpub.progressIdentity(store.nativeLibrary(),selected);
                    String digest=hex(MessageDigest.getInstance("SHA-256").digest(identity.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
                    Log.i(TAG,"bounded stored selector "+label+" sha256="+digest);
                    postUi(()->setStatus("Review selector "+label+" "+digest));
                } catch(Throwable error) { Log.e(TAG,"Review selector read failed: "+message(error)); }
            });
            return;
        }
        if(intent.getBooleanExtra("review_schema6",false)) {
            intent.removeExtra("review_schema6");
            HostTask task=beginTask(4); long gen=generation;
            worker.execute(()->{
                try {
                    closeSessionsLocked(); store.close(); store=null;
                    File file=new File(getFilesDir(),"library.db");
                    try(android.database.sqlite.SQLiteDatabase old=android.database.sqlite.SQLiteDatabase.openDatabase(file.getPath(),null,0)) {
                        old.execSQL("DROP TABLE epub_notes"); old.execSQL("DROP TABLE epub_progress"); old.execSQL("DROP TABLE epub_bounded_books");
                        old.execSQL("PRAGMA user_version=6");
                    }
                    store=new BookStore(getApplicationContext(),file);
                    try(android.database.sqlite.SQLiteDatabase current=android.database.sqlite.SQLiteDatabase.openDatabase(file.getPath(),null,android.database.sqlite.SQLiteDatabase.OPEN_READONLY);
                        android.database.Cursor cursor=current.rawQuery("PRAGMA user_version",null)) {
                        if(!cursor.moveToFirst() || cursor.getInt(0)!=7) throw new IllegalStateException("Schema migration did not reach 7");
                    }
                    postUi(()->{ if(gen==generation) { finishTask(gen); showShelf(false); setStatus("Review schema 6 upgraded to 7"); loadShelf(false); } });
                } catch(Throwable error) { taskFailed(gen,"Review migration: ",error); }
            });
            return;
        }
        if (intent.getBooleanExtra("review_recreate", false)) {
            intent.removeExtra("review_recreate");
            intent.removeExtra("review_pause");
            recreate();
            return;
        }
        String title = intent.getStringExtra("review_open_title");
        if (title != null) {
            worker.execute(()->{
                try {
                    CatalogStore.ShelfBook book=store.localShelfTitle(title);
                    postUi(()->{
                        if (book==null) setStatus("Review target is missing from the shelf");
                        else openBook(book.sdkBookId,-1,-1);
                    });
                } catch (Throwable error) { postStatus("Review shelf: "+message(error)); }
            });
        }
    }

    private boolean routeImport(Intent intent) {
        if(intent==null)return false;
        String action=intent.getAction();
        if(!Intent.ACTION_VIEW.equals(action)&&!Intent.ACTION_SEND.equals(action)&&!Intent.ACTION_SEND_MULTIPLE.equals(action))return false;
        // An incoming book brings its import/cancel control into view, including
        // a cold launch whose previous reading page would otherwise auto-restore.
        restoreReader=false;restoreBook=0;
        prefs.edit().putBoolean("lastReader",false).apply();
        if(preferencesPanel!=null)preferencesPanel.close();
        if(readingPanel!=null)readingPanel.close();
        if(searchPanel!=null)searchPanel.close();
        if(navigationPanel!=null)navigationPanel.close();
        if(operation!=1&&(currentBook!=null||operation!=0||pageBusy))leaveReader();
        else showShelf(false);
        imports.submit(intent);return true;
    }

    void importStatus(String text) { if(!destroyed)setStatus(text); }
    void importCopying(boolean copying) {
        if(destroyed)return;
        importButton.setText(copying?"Cancel import":"Import");
        importButton.setContentDescription(copying?"Cancel book import":"Import a book");
    }

    boolean importReady(ReadyRequest ready) {
        if (destroyed || worker == null || store == null || pageBusy || operation != 0) return false;
        final String name=ready.title().isEmpty()?ready.id():ready.title();
        final int format=ready.format().exrCode();
        final HostTask task = beginTask(1);
        final long gen = generation;
        showLoading("Importing " + name + "...", true);
        worker.execute(() -> {
          synchronized (IMPORT_LOCK) {
            CopyResult copied = null;
            long importedId = 0;
            boolean created = false;
            boolean published = false;
            boolean metadataFinalized = false;
            try {
                if(ready.size()>MAX_INPUT_BYTES)throw new IOException("Current reader has a 32 MiB reading limit; the 128 MiB staging ceiling does not make larger books readable");
                copied = copyUri(Uri.fromFile(ready.file()), ready.id(), task);
                if(copied.bytes!=ready.size()||!ready.id().startsWith(copied.sha256+"."))throw new IOException("Staged original identity changed");
                reviewGate("import-copied", task);
                task.check();
                String path = copied.file.getAbsolutePath();
                if (format == NativeLibrary.FORMAT_PDF) {
                    byte[] bytes = readFile(copied.file);
                    EXReader.FixedDocument document = new EXReader.Pdf(bytes, fontBytes(), 0);
                    document.close();
                } else if (format == NativeLibrary.FORMAT_CBZ) {
                    byte[] bytes = readFile(copied.file);
                    EXReader.FixedDocument document = new EXReader.FixedDocument(EXReader.FixedFormat.CBZ, bytes);
                    document.close();
                } else if(format!=NativeLibrary.FORMAT_EPUB) {
                    EXReader.Document document = new EXReader.Document(path);
                    document.close();
                }
                task.check();
                boolean legacy=BuildConfig.DEBUG && getIntent().getBooleanExtra("review_legacy_import",false);
                getIntent().removeExtra("review_legacy_import");
                NativeLibrary.ImportResult result = legacy?store.nativeLibrary().importLegacyFile(path,format,name):store.importFile(path, format, name);
                importedId = result.id;
                created = result.created;
                reviewGate("import-inserted", task);
                BookStore.VerifiedSource verified = store.verifySource(importedId, copied.sha256, copied.bytes, task);
                final long acceptedId = importedId;
                final CopyResult resultCopy = copied;
                final String oldPath = prefs.getString("path_" + acceptedId, null);
                final boolean reused = !created && matchesOwnedCopy(oldPath, copied, task);
                task.commit(() -> {
                    String acceptedPath = reused ? oldPath : path;
                    if (!prefs.edit().putString("path_" + acceptedId, acceptedPath)
                            .putLong("size_" + acceptedId, verified.bytes).commit()) {
                        throw new IOException("Could not persist the imported book path");
                    }
                });
                published = true;
                if (reused && resultCopy.owned && !path.equals(oldPath) && !resultCopy.file.delete()) {
                    Log.w(TAG, "Unused duplicate copy could not be removed");
                }
                reviewGate("import-published", task);
                store.finalizeImport(verified);
                metadataFinalized = true;
                reviewGate("import-committed", task);
                final boolean inserted = created;
                imports.completed(this,ready,true,false);
                postUi(() -> {
                    if (gen != generation) return;
                    finishTask(gen);
                    setStatus(inserted ? "Imported " + name : "Already in shelf: " + name);
                    loadShelf(false);
                });
            } catch (Throwable error) {
                Throwable reported = error;
                if (!published) {
                    try { rollbackImport(copied, importedId, created); }
                    catch (Throwable cleanup) { reported = cleanup; }
                }
                final Throwable failure = reported;
                final boolean completed = published;
                final boolean mapped = metadataFinalized;
                boolean lifecycle = error instanceof HostTask.Cancelled && destroyed;
                imports.completed(this,ready,!lifecycle && (!published || metadataFinalized),lifecycle);
                postUi(() -> {
                    if (gen != generation) return;
                    finishTask(gen);
                    setStatus(completed ? "Imported " + name + (mapped ? "" : "; metadata repair pending: " + message(failure)) : failure instanceof HostTask.Cancelled ?
                            "Import canceled" : "Could not open " + name + ": " + message(failure));
                    loadShelf(false);
                });
            }
          }
        });
        return true;
    }

    private static final class CopyResult {
        final File file;
        final boolean owned;
        final String sha256;
        final long bytes;
        CopyResult(File file, boolean owned, String sha256, long bytes) {
            this.file = file; this.owned = owned; this.sha256 = sha256; this.bytes = bytes;
        }
    }

    /** Preferences only suggest a reusable path; actual private bytes must match. */
    private boolean matchesOwnedCopy(String path, CopyResult copy, HostTask task) throws IOException {
        if (path == null) return false;
        try {
            File file = new File(path).getCanonicalFile();
            File folder = new File(getFilesDir(), "books").getCanonicalFile();
            if (!folder.equals(file.getParentFile()) || !file.isFile() || file.length() != copy.bytes) return false;
            MessageDigest digest;
            try { digest = MessageDigest.getInstance("SHA-256"); }
            catch (Exception impossible) { throw new AssertionError(impossible); }
            long bytes = 0;
            try (InputStream input = new FileInputStream(file)) {
                byte[] chunk = new byte[65536]; int read;
                while ((read = input.read(chunk)) != -1) {
                    task.check();
                    bytes += read;
                    if (bytes > copy.bytes) return false;
                    digest.update(chunk, 0, read);
                }
            }
            task.check();
            return bytes == copy.bytes && copy.sha256.equals(hex(digest.digest()));
        } catch (HostTask.Cancelled error) { throw error; }
        catch (IOException inaccessible) { return false; }
    }

    private void rollbackImport(CopyResult copy, long id, boolean created) throws IOException {
        if (created) {
            try { store.deleteBook(id); }
            catch (Throwable error) {
                throw new IOException("Import rollback failed; retained book " + id + " and its source: " + message(error));
            }
        }
        if (copy != null && copy.owned && copy.file.exists() && !copy.file.delete()) {
            throw new IOException("Import cleanup failed; retained source " + copy.file.getName());
        }
    }

    private CopyResult copyUri(Uri uri, String name, HostTask task) throws IOException {
        task.check();
        File folder = new File(getFilesDir(), "books");
        if (!folder.isDirectory() && !folder.mkdirs()) throw new IOException("Cannot create the book folder");
        File temporary = new File(folder, "import-" + System.nanoTime() + ".part");
        ContentResolver resolver = getContentResolver();
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (Exception error) {
            throw new IOException("SHA-256 is unavailable");
        }
        long total = 0;
        try (InputStream input = resolver.openInputStream(uri);
             FileOutputStream output = new FileOutputStream(temporary)) {
            if (input == null) throw new IOException("The picker returned an unreadable source");
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) > 0) {
                task.check();
                total += count;
                if (total > MAX_INPUT_BYTES) throw new IOException("File exceeds 32 MiB limit");
                output.write(buffer, 0, count);
                if(total==count)reviewGate("import-stable-partial",task);
                digest.update(buffer, 0, count);
            }
            output.getFD().sync();
        } catch (HostTask.Cancelled canceled) {
            removeTemporary(temporary);
            throw canceled;
        } catch (Throwable error) {
            removeTemporary(temporary);
            if (error instanceof IOException) throw (IOException) error;
            throw new IOException(message(error));
        }
        if (total == 0) {
            removeTemporary(temporary);
            throw new IOException("The selected file is empty");
        }
        String extension = extension(name);
        String sourceHash = hex(digest.digest());
        File target = new File(folder, sourceHash + (extension.isEmpty() ? "" : "." + extension));
        if (target.isFile()) {
            CopyResult expected=new CopyResult(target,false,sourceHash,total);
            if(!matchesOwnedCopy(target.getPath(),expected,task)) {
                removeTemporary(temporary);
                throw new IOException("Existing private original does not match its content identity");
            }
            if (!temporary.delete()) throw new IOException("Cannot clean the duplicate temporary file");
            return new CopyResult(target, false, sourceHash, total);
        } else if (!temporary.renameTo(target)) {
            removeTemporary(temporary);
            throw new IOException("Cannot keep the app-owned copy");
        }
        return new CopyResult(target, true, sourceHash, total);
    }

    private static void removeTemporary(File temporary) throws IOException {
        if (temporary.exists() && !temporary.delete())
            throw new IOException("Import cleanup failed; retained temporary source " + temporary.getName());
    }

    /** Called under IMPORT_LOCK, after any previous Activity's import has finished. */
    private void cleanImportTemporaries() throws IOException {
        File folder=new File(getFilesDir(),"books").getCanonicalFile();
        File[] files=folder.listFiles();
        if(files==null)return;
        for(File file:files)if(file.getName().matches("import-[0-9]+\\.part")&&file.isFile()
                &&file.getAbsoluteFile().equals(file.getCanonicalFile())&&!file.delete())
            throw new IOException("Cannot clean a previous unfinished private book copy");
    }

    private String queryName(Uri uri) {
        String name = null;
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) name = cursor.getString(index);
            }
        } catch (Throwable ignored) {
        }
        if (name == null || name.isEmpty()) {
            name = uri.getLastPathSegment();
            if (name == null || name.isEmpty()) name = "Untitled";
        }
        return name;
    }

    private long querySize(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.SIZE}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.SIZE);
                if (index >= 0 && !cursor.isNull(index)) return cursor.getLong(index);
            }
        } catch (Throwable ignored) {
        }
        return -1;
    }

    static int formatFor(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".epub")) return NativeLibrary.FORMAT_EPUB;
        if (lower.endsWith(".pdf")) return NativeLibrary.FORMAT_PDF;
        if (lower.endsWith(".txt")) return NativeLibrary.FORMAT_TXT;
        if (lower.endsWith(".html") || lower.endsWith(".htm") || lower.endsWith(".xhtml")) return NativeLibrary.FORMAT_HTML;
        if (lower.endsWith(".fb2")) return NativeLibrary.FORMAT_FB2;
        if (lower.endsWith(".docx")) return NativeLibrary.FORMAT_DOCX;
        if (lower.endsWith(".rtf")) return NativeLibrary.FORMAT_RTF;
        if (lower.endsWith(".mobi") || lower.endsWith(".azw3")) return NativeLibrary.FORMAT_MOBI;
        if (lower.endsWith(".cbz")) return NativeLibrary.FORMAT_CBZ;
        return -1;
    }

    static String formatName(int format) {
        switch (format) {
            case NativeLibrary.FORMAT_TXT: return "TXT";
            case NativeLibrary.FORMAT_HTML: return "HTML";
            case NativeLibrary.FORMAT_FB2: return "FB2";
            case NativeLibrary.FORMAT_EPUB: return "EPUB";
            case NativeLibrary.FORMAT_DOCX: return "DOCX";
            case NativeLibrary.FORMAT_RTF: return "RTF";
            case NativeLibrary.FORMAT_MOBI: return "MOBI";
            case NativeLibrary.FORMAT_PDF: return "PDF";
            case NativeLibrary.FORMAT_CBZ: return "CBZ";
            default: return "FORMAT " + format;
        }
    }

    private static String extension(String name) {
        int dot = name.lastIndexOf('.');
        return dot >= 0 && dot + 1 < name.length() ? name.substring(dot + 1).toLowerCase(Locale.ROOT) : "";
    }

    private static String hex(byte[] bytes) {
        StringBuilder builder = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) builder.append(String.format(Locale.US, "%02x", value));
        return builder.toString();
    }

    private static String humanBytes(long bytes) {
        if (bytes <= 0) return "size unknown";
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format(Locale.US, "%.1f KiB", bytes / 1024.0);
        return String.format(Locale.US, "%.1f MiB", bytes / (1024.0 * 1024.0));
    }

    private byte[] fontBytes() throws IOException {
        if (FONT == null) FONT = loadFontAsset();
        if (FONT == null || FONT.length == 0) throw new IOException("The bundled font is missing");
        return FONT;
    }

    private byte[] loadFontAsset() {
        try (InputStream input = getAssets().open("Reader.otf");
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) > 0) output.write(buffer, 0, count);
            return output.toByteArray();
        } catch (Throwable error) {
            Log.e(TAG, "font asset missing: " + message(error));
            return new byte[0];
        }
    }

    private static byte[] readFile(File file) throws IOException {
        if (file.length() > MAX_INPUT_BYTES) throw new IOException("File exceeds 32 MiB limit");
        ByteArrayOutputStream output = new ByteArrayOutputStream((int) Math.max(1024, file.length()));
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) > 0) output.write(buffer, 0, count);
        }
        return output.toByteArray();
    }

    private void updateSdkLabel() {
        try {
            sdkLabel.setText("EXReader " + NativeLibrary.identity() + " · " + Build.SUPPORTED_ABIS[0]);
        } catch (Throwable error) {
            sdkLabel.setText("Native library unavailable: " + message(error));
        }
    }

    private void showLoading(String text, boolean cancelable) {
        loadingText.setText(text);
        cancelButton.setVisibility(cancelable ? View.VISIBLE : View.GONE);
        loadingOverlay.setVisibility(View.VISIBLE);
    }

    private void hideLoading() {
        loadingOverlay.setVisibility(View.GONE);
    }

    private void setStatus(String text) {
        statusText.setText(text);
        if (readerStatus != null) readerStatus.setText(text);
        Log.i(TAG, "status " + text);
    }

    private void postStatus(String text) {
        postUi(() -> setStatus(text));
    }

    private void postUi(Runnable action) {
        ui.post(() -> {
            if (destroyed) return;
            try {
                action.run();
            } catch (Throwable error) {
                Log.e(TAG, "UI action failed: " + message(error));
            }
        });
    }

    private static String message(Throwable error) {
        if (error == null) return "unknown error";
        String text = error.getMessage();
        if (error instanceof org.exreader.EXReaderException) {
            int code = ((org.exreader.EXReaderException) error).code;
            return (text == null || text.isEmpty() ? "engine error" : text) + " (code " + code + ")";
        }
        return text == null || text.isEmpty() ? error.getClass().getSimpleName() : text;
    }

    private void saveInstancePrefs() {
        if (catalogShelf!=null) catalogShelf.save();
        prefs.edit().putLong("lastBook", bookId)
                .putBoolean("lastReader", readerPanel.getVisibility() == View.VISIBLE)
                .putFloat("font", fontSize).putFloat("zoom", zoom).apply();
    }

    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putLong("bookId", currentBook == null ? 0 : currentBook.id);
        out.putLong("offset", current == null ? -1 : current.start);
        out.putInt("page", current == null ? -1 : current.index);
        out.putFloat("font", fontSize);
        out.putFloat("zoom", zoom);
        out.putBoolean("reader", readerPanel.getVisibility() == View.VISIBLE);
        saveInstancePrefs();
    }

    @Override protected void onStop() {
        if(preferencesPanel!=null)preferencesPanel.close();
        if(readingPanel!=null)readingPanel.close();
        if(searchPanel!=null)searchPanel.close();
        if(navigationPanel!=null)navigationPanel.close();
        if(syncPanel!=null)syncPanel.background();
        super.onStop();
        saveInstancePrefs();
    }

    @Override public void onBackPressed() {
        if(preferencesPanel!=null&&preferencesPanel.visible()){preferencesPanel.close();return;}
        if(readingPanel!=null&&readingPanel.visible()){readingPanel.close();return;}
        if(navigationPanel!=null&&navigationPanel.visible()){navigationPanel.close();return;}
        if(searchPanel!=null&&searchPanel.visible()){searchPanel.close();return;}
        if(organizationPanel!=null&&organizationPanel.visible()){organizationPanel.hide();return;}
        if (notesPanel.getVisibility() == View.VISIBLE) {
            hideNotes();
            return;
        }
        if (readerPanel.getVisibility() == View.VISIBLE) {
            leaveReader();
            return;
        }
        super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if(imports!=null)imports.detach(this);
        if(preferencesPanel!=null)preferencesPanel.close();
        if(readingPanel!=null)readingPanel.close();
        if(searchPanel!=null)searchPanel.close();
        if(navigationPanel!=null)navigationPanel.close();
        if(syncPanel!=null)syncPanel.close();
        if(organizationPanel!=null)organizationPanel.close();
        if (shelfMetrics!=null) shelfMetrics.close();
        if (catalogShelf!=null) catalogShelf.close();
        destroyed = true;
        if (activeTask != null) activeTask.cancel();
        ++generation;
        final ExecutorService service = worker;
        worker = null;
        if (service != null) {
            service.execute(() -> {
                try { closeSessionsLocked(); }
                finally {
                    if (store != null) { store.close(); store = null; }
                    Log.i(TAG, "worker shutdown complete");
                }
            });
            service.shutdown();
        }
        super.onDestroy();
    }

    private ReadingRequests readingRequests(){if(readingRequests==null)readingRequests=new ReadingRequests(getFilesDir());return readingRequests;}
    private ReadingControl readingControl(HostTask task,String stage){return new ReadingControl(task,getFilesDir(),stage,BuildConfig.DEBUG&&getIntent().getBooleanExtra("exr_reading_gate",false));}
    private interface ReadingCall<T>{T run()throws Exception;}
    private <T> void readingCall(HostTask task,ReadingCall<T> action,java.util.function.Consumer<T> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        owner.execute(()->{try{task.check();if(store==null)throw new HostTask.Cancelled();T value=action.run();task.check();done.accept(value);}catch(Throwable error){failed.accept(error);}});
    }
    private String readingBook(long book,HostTask task)throws Exception {
        task.check();if(sessionBookId!=book)throw new HostTask.Cancelled();BookStore.VerifiedSource source=store.verifySource(book,null,0,task);CatalogStore.ShelfBook local=store.localShelfBook(book);if(local==null||!source.key.equals(local.key.bookKey)||source.bytes!=local.sourceBytes)throw new IOException("Reading original no longer matches this book");return source.key;
    }
    @Override public void releaseReading(){readingFrame=null;readingSelection=null;ExecutorService owner=worker;if(owner!=null&&!owner.isShutdown())owner.execute(()->readingHistory=null);}
    @Override public void readingList(long book,String after,HostTask task,java.util.function.Consumer<ReadingPanel.State> done,java.util.function.Consumer<Throwable> failed){
        readingCall(task,()->{String key=readingBook(book,task);NativeReadingProduct.Page page=NativeReadingProduct.list(store,key,after,false,readingControl(task,"list"));ReadingRequests.Pending pending=null;boolean corrupt=false;try{pending=readingRequests().read();}catch(Exception error){corrupt=true;}return new ReadingPanel.State(page,pending,corrupt);},done,failed);
    }
    private ReadingRecord readingSelected(long book,ReadingRecord selected,HostTask task)throws Exception {
        String key=readingBook(book,task);if(selected==null||selected.state!=ReadingRecord.SAFE||!key.equals(selected.bookKey))throw new IOException("Please refresh and explicitly select a safe reading record");
        ReadingRecord fresh=NativeReadingProduct.selected(store,key,selected.id,selected.head,selected.kind==ReadingRecord.PROGRESS,readingControl(task,"selected"));if(fresh.state!=ReadingRecord.SAFE||!fresh.head.equals(selected.head)||!fresh.sha.equals(selected.sha))throw new IOException("Reading record changed; refresh");return fresh;
    }
    private NativeReadingSdk.Match resolveReadingLocation(long book,ReadingCapture capture,float size,HostTask task)throws Exception{
        String key=readingBook(book,task);if(!key.equals(capture.bookKey))throw new IOException("Reading selector belongs to another original");
        NativeReadingSdk.Match independent=NativeReadingSdk.resolve(store,book,capture,fontBytes(),size,task,readingControl(task,"resolve"));
        if(fixed==null||!fixed.cbz())return independent;
        if(!key.equals(fixed.sourceKey()))throw new IOException("Current CBZ renderer belongs to another original");
        NativeReadingSdk.Match actual=fixed.resolveCurrent(capture,task);
        if(!readingBook(book,task).equals(key))throw new IOException("CBZ original changed during location verification");
        if(!independent.found()||!actual.found())return independent.found()?actual:independent;
        ReadingCapture a=independent.recaptured,b=actual.recaptured;
        if(independent.unit!=actual.unit||independent.start!=actual.start||independent.end!=actual.end||!key.equals(b.bookKey)||!a.parser.equals(b.parser)||!a.pageId.equals(b.pageId)||!java.util.Arrays.deepEquals(a.bytes(),b.bytes()))throw new IOException("Independent and current CBZ page identities differ");
        return actual;
    }
    @Override public void readingResolve(long book,ReadingRecord selected,HostTask task,java.util.function.Consumer<NativeReadingSdk.Match> done,java.util.function.Consumer<Throwable> failed){
        final float size=fontSize;readingCall(task,()->{ReadingRecord fresh=readingSelected(book,selected,task);if(!fresh.readable())throw new IOException("This record has no current readable location");return resolveReadingLocation(book,fresh.capture,size,task);},done,failed);
    }
    @Override public void readingHistory(long book,ReadingRecord selected,boolean first,HostTask task,java.util.function.Consumer<ReadingHistory.Page> done,java.util.function.Consumer<Throwable> failed){
        readingCall(task,()->{ReadingRecord fresh=readingSelected(book,selected,task);if(!fresh.deleted)throw new IOException("Explicit restore requires the current tombstone");if(first)readingHistory=new ReadingHistory(fresh.bookKey,fresh.id,fresh.head,fresh.kind==ReadingRecord.PROGRESS);if(readingHistory==null)throw new IOException("Please reopen retained versions");return readingHistory.next(store,readingControl(task,"history"));},done,failed);
    }
    @Override public void readingWrite(long book,ReadingPanel.Action action,HostTask task,java.util.function.Consumer<NativeReadingProduct.Result> done,java.util.function.Consumer<Throwable> failed){
        final PageSnapshot frame=readingFrame;final Selection selectedRange=readingSelection;final float size=fontSize;final String originalPath=prefs.getString("path_"+book,null);
        readingCall(task,()->{
            if(readingRequests().read()!=null)throw new IOException("A previous reading request still needs confirmation");String key=readingBook(book,task);if(frame==null||frame.bookId!=book||!key.equals(frame.sourceKey))throw new IOException("Displayed reading frame changed");
            ReadingCapture.encode(action.body,65536);if(action.body.indexOf('\0')>=0)throw new IllegalArgumentException("Reading body contains NUL");
            boolean progress=action.kind==NativeReadingProduct.PROGRESS;ReadingRecord fresh=null;String id="";String[] heads=new String[0];int mode=frame.fixed?ReadingCapture.FIXED:frame.bounded?ReadingCapture.EPUB:ReadingCapture.REFLOW;ReadingCapture capture=null;
            if(action.target!=null&&action.target.state==ReadingRecord.SAFE){fresh=readingSelected(book,action.target,task);id=fresh.id;heads=new String[]{fresh.head};mode=fresh.mode;}
            else if(action.target!=null&&action.target.state!=ReadingRecord.MISSING)throw new IOException("Unsafe reading graph cannot be chosen automatically");
            if(action.operation==NativeReadingProduct.RESTORE){
                if(fresh==null||!fresh.deleted||action.version==null)throw new IOException("Choose a retained version and current tombstone explicitly");ReadingVersion retained=NativeReadingProduct.version(store,key,id,action.version.id,progress,readingControl(task,"history"));if(!retained.sha.equals(action.version.sha)||!retained.restorable())throw new IOException("Retained version changed");NativeReadingSdk.Match match=resolveReadingLocation(book,retained.capture,size,task);if(!match.found())throw new IOException("Retained location is not FOUND; nothing restored");capture=match.recaptured;mode=capture.mode;
            }else if(action.operation==NativeReadingProduct.DELETE||action.kind==NativeReadingProduct.NOTE_TEXT){
                if(fresh==null||fresh.deleted)throw new IOException("Select a current live reading head");
            }else{
                if(fresh!=null&&fresh.deleted)throw new IOException("Deleted records require explicit restore");long start=frame.start,end=start;if(action.kind==NativeReadingProduct.HIGHLIGHT){if(selectedRange==null||selectedRange.pageIndex!=frame.index||selectedRange.end<=selectedRange.start)throw new IOException("Select actual page text first");start=selectedRange.start;end=selectedRange.end;}
                capture=NativeReadingSdk.capture(store,frame,start,end,fontBytes(),size,originalPath==null?null:new File(originalPath),task,readingControl(task,"capture"));mode=capture.mode;if(!progress&&id.isEmpty())id=ReadingRequests.newId();
                if(fixed!=null&&fixed.cbz()){
                    NativeReadingSdk.Match actual=resolveReadingLocation(book,capture,size,task);
                    if(!actual.found()||!frame.fixedTextProvided||frame.fixedRendererIdentity!=fixed.rendererIdentity()||actual.unit!=frame.index||frame.fixedPageId==null||!frame.fixedPageId.equals(actual.recaptured.pageId))throw new IOException("Displayed CBZ page is not independently FOUND in the current renderer");
                    capture=actual.recaptured;
                }
            }
            ReadingRequests.Pending pending=new ReadingRequests.Pending(book,key,id,ReadingRequests.newId(),ReadingRequests.newId(),heads,action.kind,action.operation,mode,capture,action.body);task.check();readingRequests().save(pending);
            try{task.check();return commitReading(pending,task);}catch(HostTask.Cancelled cancelled){readingRequests().clear(pending.revision);throw cancelled;}
        },done,failed);
    }
    private NativeReadingProduct.Result commitReading(ReadingRequests.Pending pending,HostTask task)throws Exception {
        if(!readingBook(pending.sdkBook,task).equals(pending.book))throw new IOException("Pending request belongs to another original");final NativeReadingProduct.Result[] result={null};
        if(fixed!=null&&fixed.cbz()&&pending.capture!=null&&!resolveReadingLocation(pending.sdkBook,pending.capture,fontSize,task).found())throw new IOException("Pending CBZ location is not FOUND in both source and current renderer");
        task.commit(()->{String[] selection=NativeCatalog.selection(store.productOwner(),"book",pending.book);if("0".equals(selection[0])){NativeCatalog.Result bootstrap=store.bootstrapBook(pending.sdkBook,pending.bootstrap,new String[0],task);if(bootstrap.status!=NativeCatalog.Result.OK)throw new IOException("Book metadata could not be prepared for the reading request");}
            result[0]=NativeReadingProduct.apply(store,pending.revision,pending.expected,pending.kind,pending.operation,pending.book,pending.id,pending.mode,pending.capture,pending.body);
        });
        ReadingControl committed=readingControl(task,"committed");committed.check();committed.check();committed.check();readingRequests().clear(pending.revision);return result[0];
    }
    @Override public void readingRetry(long book,HostTask task,java.util.function.Consumer<NativeReadingProduct.Result> done,java.util.function.Consumer<Throwable> failed){
        readingCall(task,()->{ReadingRequests.Pending pending=readingRequests().read();if(pending==null||pending.sdkBook!=book||!readingBook(book,task).equals(pending.book))throw new IOException("Open the original book for this pending request");return commitReading(pending,task);},done,failed);
    }
    @Override public void readingDiscard(HostTask task,Runnable done,java.util.function.Consumer<Throwable> failed){readingCall(task,()->{task.check();readingRequests().clear();return true;},ignored->done.run(),failed);}
    @Override public void navigateReading(long book,NativeReadingSdk.Match match){
        if(!match.found()||currentBook==null||currentBook.id!=book||current==null||operation!=0||pageBusy||match.unit<0||match.unit>Integer.MAX_VALUE||match.start<0||match.end<match.start)return;final float scale=zoom;final boolean isFixed=current.fixed;
        runPage(task->{
            if(!readingBook(book,task).equals(match.recaptured.bookKey))throw new IOException("Reading original changed before navigation");
            NativeReadingSdk.Match location=isFixed&&fixed.cbz()?resolveReadingLocation(book,match.recaptured,fontSize,task):match;if(!location.found())throw new IOException("Current CBZ renderer cannot confirm the selected page");
            PageLoad load=isFixed?fixed.load((int)location.unit,scale,task):reflow.seekReading(location,task);
            try{if(load!=null){if(isFixed&&fixed.cbz()&&(!location.recaptured.pageId.equals(load.snapshot.fixedPageId)||!readingBook(book,task).equals(location.recaptured.bookKey)))throw new IOException("Rendered CBZ page/source changed before publication");load.snapshot.highlightStart=location.recaptured.start;load.snapshot.highlightEnd=location.recaptured.end;}return load;}
            catch(Exception|Error error){if(load!=null)load.close();throw error;}
        },()->setStatus("已跳转到阅读记录"),"阅读位置不可用");
    }

    private void closeDirectoryNative(){if(navigation!=null){navigation.close();navigation=null;}}
    @Override public void releaseDirectory(){ExecutorService owner=worker;if(owner!=null&&!owner.isShutdown())owner.execute(this::closeDirectoryNative);}
    private NativeNavigation.Control directoryControl(HostTask task){return new NativeNavigation.Control(task,getFilesDir(),BuildConfig.DEBUG&&getIntent().getBooleanExtra("exr_navigation_gate",false));}
    @Override public void directory(long book,HostTask task,java.util.function.Consumer<NativeNavigation.Info> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        owner.execute(()->{try{task.check();closeDirectoryNative();navigation=new NativeNavigation(store,book,fontBytes(),task,directoryControl(task));NativeNavigation.Info info=navigation.info();task.check();done.accept(info);}catch(Throwable error){closeDirectoryNative();failed.accept(error);}});
    }
    @Override public void directoryPage(long book,long parent,long first,HostTask task,java.util.function.Consumer<NativeNavigation.Page> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        owner.execute(()->{try{task.check();if(navigation==null||navigation.book!=book)throw new HostTask.Cancelled();NativeNavigation.Page page=navigation.page(parent,first);task.check();done.accept(page);}catch(Throwable error){failed.accept(error);}});
    }
    @Override public void directoryResolve(long book,long row,long part,String cfi,HostTask task,java.util.function.Consumer<NativeNavigation.Destination> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        final float requestedFont=fontSize;
        owner.execute(()->{try{task.check();if(navigation==null||navigation.book!=book)throw new HostTask.Cancelled();NativeNavigation.Destination target=navigation.resolve(store,row,part,cfi,fontBytes(),requestedFont,task,directoryControl(task));task.check();done.accept(target);}catch(Throwable error){failed.accept(error);}});
    }
    @Override public void navigateDirectory(NativeNavigation.Destination destination){
        NativeNavigation.Result target=destination.result;
        if((target.status!=NativeNavigation.OK&&target.status!=NativeNavigation.PART_ONLY)||currentBook==null||currentBook.id!=destination.book||current==null||operation!=0||pageBusy||target.part<0||target.part>Integer.MAX_VALUE||target.offset<0)return;
        final boolean isFixed=current.fixed;final float scale=zoom;
        runPage(task->{BookStore.VerifiedSource source=store.verifySource(destination.book,null,0,task);if(!(source.key+"@exreader-sdk-"+NativeNavigation.nativeParser()).equals(destination.key))throw new IOException("目录原件已改变");return isFixed?fixed.load((int)target.part,scale,task):reflow.seekNavigation(destination,task);},()->setStatus("已跳转到目录目标"),"目录目标不可用");
    }
    private void closeSearchNative(){if(search!=null){search.close();search=null;}}
    @Override public void releaseSearch(){ExecutorService owner=worker;if(owner!=null&&!owner.isShutdown())owner.execute(this::closeSearchNative);}
    @Override public void scan(long book,String query,boolean next,HostTask task,java.util.function.Consumer<NativeSearch.Batch> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        final boolean gate=BuildConfig.DEBUG&&getIntent().getBooleanExtra("exr_search_gate",false);
        final float searchFont=fontSize;
        owner.execute(()->{try{
            task.check();if(store==null)throw new HostTask.Cancelled();NativeSearch.validate(query);
            NativeSearch.Control control=new NativeSearch.Control(task,getFilesDir(),gate);
            if(!next){closeSearchNative();search=new NativeSearch(store,book,query,fontBytes(),searchFont,task,control);}
            else if(search==null||search.bookId!=book)throw new IllegalStateException("请重新搜索这本书");
            NativeSearch.Batch batch=search.next(control);if(batch.complete)closeSearchNative();task.check();done.accept(batch);
        }catch(Throwable error){closeSearchNative();failed.accept(error);}});
    }
    @Override public void resolve(long book,NativeSearch.Hit hit,HostTask task,java.util.function.Consumer<NativeSearch.Match> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        final float searchFont=fontSize;
        owner.execute(()->{try{task.check();if(store==null)throw new HostTask.Cancelled();NativeSearch.Match match=NativeSearch.resolve(store,book,hit,fontBytes(),searchFont,task);task.check();done.accept(match);}catch(Throwable error){failed.accept(error);}});
    }
    @Override public void navigate(long book,NativeSearch.Hit hit,NativeSearch.Match match){
        if(match.state!=NativeSearch.FOUND||currentBook==null||currentBook.id!=book||current==null||operation!=0||pageBusy)return;
        if(match.unit<0||match.unit>Integer.MAX_VALUE||match.start<0||match.end<match.start){setStatus("搜索位置不可用");return;}
        final boolean isFixed=current.fixed;final float scale=zoom;
        runPage(task->{PageLoad load=isFixed?fixed.load((int)match.unit,scale,task):reflow.seekSearch(hit,match,task);if(load!=null){load.snapshot.highlightStart=match.start;load.snapshot.highlightEnd=match.end;}return load;},()->setStatus("已跳转到搜索结果"),"搜索位置不可用");
    }
    @Override public void prepareOriginals(HostTask task,Runnable done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed){failed.accept(new HostTask.Cancelled());return;}
        owner.execute(()->{try{task.check();if(store==null)throw new IOException("书库仍在打开");store.stageSyncOriginals(new File(getFilesDir(),"sync-originals"),getSharedPreferences("sync-requests",MODE_PRIVATE),task);task.check();done.run();}catch(Throwable error){failed.accept(error);}});
    }
    @Override public void receive(NativeSync.RemoteBook book,File cached,HostTask task,java.util.function.Consumer<Long> done,java.util.function.Consumer<Throwable> failed){
        ExecutorService owner=worker;if(owner==null||destroyed||operation!=0||pageBusy){failed.accept(new IllegalStateException("请先完成当前操作"));return;}
        owner.execute(()->{synchronized(IMPORT_LOCK){try{
            task.check();if(destroyed||store==null)throw new HostTask.Cancelled();
            String sort=java.text.Normalizer.normalize(book.title,java.text.Normalizer.Form.NFC);String product=new File(getFilesDir(),"reader-catalog.db").getAbsolutePath();
            String[] selected=NativeSync.project(product,book.key,book.revision,sort);
            if(selected==null||selected.length!=7||!selected[1].equals(book.key)||!selected[0].equals(book.format)||Long.parseLong(selected[4])!=book.bytes)throw new IOException("书籍的同步记录已改变，请刷新后重试");
            if(cached.length()!=book.bytes||!BookStore.syncFileHash(cached,task).equals(book.sha))throw new IOException("接收的原件校验失败");
            closeSessionsLocked();task.check();int format=0;for(int candidate=NativeLibrary.FORMAT_TXT;candidate<=NativeLibrary.FORMAT_CBZ;candidate++)if(formatName(candidate).equalsIgnoreCase(book.format))format=candidate;
            if(format==0)throw new IOException("暂不支持这种书籍格式");
            NativeLibrary.ImportResult imported=store.importFile(cached.getAbsolutePath(),format,book.title);
            BookStore.VerifiedSource verified=store.verifySource(imported.id,book.sha,book.bytes,task);
            task.commit(()->{
                NativeSync.project(product,book.key,book.revision,sort);
                if(!prefs.edit().putString("path_"+imported.id,cached.getAbsolutePath()).putLong("size_"+imported.id,book.bytes).commit())throw new IOException("接收记录保存失败，可重试");
                store.finalizeImport(verified);
            });
            postUi(()->loadShelf(false));done.accept(imported.id);
        }catch(Throwable error){failed.accept(error);}}});
    }

    private File preferencesFile(){return new File(new File(getFilesDir(),"reading-settings"),"preferences.json");}
    private int systemTheme(){return (getResources().getConfiguration().uiMode&android.content.res.Configuration.UI_MODE_NIGHT_MASK)==android.content.res.Configuration.UI_MODE_NIGHT_YES?2:1;}
    @Override public ReadingPreferences preferences(){return readingPreferences;}
    @Override public void preferencesCancel(){if(activeTask!=null)activeTask.cancel();}
    @Override public void preferencesApply(ReadingPreferences value,Runnable done,java.util.function.Consumer<Throwable> failed){
        if(worker==null||current==null||operation!=0||pageBusy||!BuildConfig.READER_PREFERENCES){failed.accept(new IllegalStateException("请先完成当前阅读操作"));return;}
        final PageSnapshot frame=current;final long book=frame.bookId;final String path=prefs.getString("path_"+book,null);final int system=systemTheme();
        final HostTask task=beginTask(3);final long gen=generation;
        worker.execute(()->{
            PageLoad load=null;ReflowSession candidate=null;boolean transferred=false;
            try{
                task.check();if(sessionBookId!=book)throw new HostTask.Cancelled();NativePreferences.validate(value);
                if(NativePreferences.effectiveTheme(value,system)==2)throw new IOException("深色阅读页暂不可用，设置未保存");
                if(frame.fixed){load=fixed.load(frame.index,value.zoom/100f,task);}
                else{
                    ReadingControl control=new ReadingControl(task,null,"preferences-location",false);
                    ReadingCapture point=NativeReadingSdk.capture(store,frame,frame.start,frame.start,fontBytes(),fontSize,path==null?null:new File(path),task,control);
                    NativeReadingSdk.Match resolved=NativeReadingSdk.resolve(store,book,point,fontBytes(),value.font,task,control);
                    if(!resolved.found()&&resolved.state==NativeReadingSdk.AMBIGUOUS){
                        // A repeated legacy chapter can make an empty page-start
                        // point ambiguous. Capture a genuine visible range; it
                        // must independently resolve uniquely at the same start.
                        long limit=Math.min(frame.end,frame.start+65536L),end=frame.start;
                        if(frame.end<=limit)end=frame.end;else for(long boundary:frame.ends)if(boundary>end&&boundary<=limit)end=boundary;
                        if(end>frame.start){
                            point=NativeReadingSdk.capture(store,frame,frame.start,end,fontBytes(),fontSize,path==null?null:new File(path),task,control);
                            resolved=NativeReadingSdk.resolve(store,book,point,fontBytes(),value.font,task,control);
                        }
                    }
                    if(!resolved.found())throw new IOException("当前位置未精确定位，设置未保存");
                    candidate=frame.bounded?new ReflowSession(store,book,fontBytes(),value):new ReflowSession(book,path,fontBytes(),value);
                    load=candidate.seekReading(resolved,task);if(load!=null){load.snapshot.preferencesPoint=resolved.start;load.snapshot.preferencesRangeEnd=resolved.end;}
                }
                if(load==null)throw new IOException("没有可显示页面，设置未保存");
                load.snapshot.sourceKey=frame.sourceKey;
                ReadingControl gate=new ReadingControl(task,getFilesDir(),"preferences",BuildConfig.DEBUG&&getIntent().getBooleanExtra("exr_preferences_gate",false));gate.check();gate.check();gate.check();
                final PageLoad ready=load;final ReflowSession newReflow=candidate;
                synchronized(PREFERENCES_LOCK){
                    task.check();if(destroyed||ownerEpoch!=OWNER_EPOCH.get())throw new HostTask.Cancelled();
                    task.commit(()->{
                        // Save is the only fallible publication. No SDK progress or
                        // product mutation follows it; the old exact point remains saved.
                        NativePreferences.save(value,preferencesFile().getPath(),task);
                        ready.accept();if(newReflow!=null){ReflowSession old=reflow;reflow=newReflow;if(old!=null)old.close();}
                        readingPreferences=value;preferencesLoadError=null;
                    });
                }
                transferred=true;final PageLoad delivered=load;
                postUi(()->{if(gen!=generation)return;fontSize=value.font;zoom=value.zoom/100f;readerView.setTurnPreferences(value.direction,value.input);applyPage(gen,delivered,null);setStatus("阅读设置已保存");done.run();});
            }catch(Throwable error){postUi(()->{if(gen!=generation)return;finishTask(gen);setStatus(error instanceof HostTask.Cancelled?"设置已取消，保留原页":message(error));failed.accept(error);});}
            finally{if(load!=null)load.close();if(!transferred&&candidate!=null)candidate.close();}
        });
    }
    @Override public boolean dispatchKeyEvent(android.view.KeyEvent event){
        int code=event.getKeyCode();
        if(BuildConfig.DEBUG&&BuildConfig.READER_PREFERENCES&&(code==19||code==20||code==21||code==22||code==92||code==93))Log.i(TAG,"preferences key code="+code+" action="+event.getAction()+" repeat="+event.getRepeatCount()+" input="+(readingPreferences==null?0:readingPreferences.input)+" operation="+operation+" selected="+(readerView!=null&&readerView.isSelectMode())+" focus="+hasWindowFocus());
        if(BuildConfig.READER_PREFERENCES&&readingPreferences!=null&&readingPreferences.input==4&&current!=null&&!readerView.isSelectMode()&&operation==0&&readerPanel.getVisibility()==View.VISIBLE){
            int delta=0;if(code==android.view.KeyEvent.KEYCODE_PAGE_DOWN||code==android.view.KeyEvent.KEYCODE_DPAD_DOWN)delta=1;
            else if(code==android.view.KeyEvent.KEYCODE_PAGE_UP||code==android.view.KeyEvent.KEYCODE_DPAD_UP)delta=-1;
            else if(readingPreferences.direction!=3&&code==android.view.KeyEvent.KEYCODE_DPAD_RIGHT)delta=readingPreferences.direction==2?-1:1;
            else if(readingPreferences.direction!=3&&code==android.view.KeyEvent.KEYCODE_DPAD_LEFT)delta=readingPreferences.direction==2?1:-1;
            if(delta!=0){if(event.getAction()==android.view.KeyEvent.ACTION_DOWN&&event.getRepeatCount()==0)turnPage(delta);return true;}
        }
        return super.dispatchKeyEvent(event);
    }
    @Override public void onTapZone(int delta) {
        turnPage(delta);
    }

    @Override public void onSelectionChanged(Selection selection) {
        FrameLayout.LayoutParams position=(FrameLayout.LayoutParams)selectionBar.getLayoutParams();
        int gravity=readerView.selectionInLowerHalf()?Gravity.TOP:Gravity.BOTTOM;
        if(position.gravity!=gravity){position.gravity=gravity;selectionBar.setLayoutParams(position);}
        selectionBar.setVisibility(View.VISIBLE);
        selectionStatus.setText("Selected: " + ReaderView.clip(selection.text, 80));
    }

    @Override public void onSelectionCleared() {
        selectionBar.setVisibility(View.GONE);
        selectionStatus.setText("");
    }

    @Override public void onSelectModeChanged(boolean enabled) {
        selectButton.setText(enabled ? "Selecting" : "Select");
        setStatus(enabled ? "Select mode on" : "Select mode off");
    }
}
