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
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import org.exreader.EXReader;

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

/**
 * Single-activity Android host. All SDK access runs on one worker thread; the UI
 * only receives immutable page snapshots and never touches a native handle.
 */
public final class MainActivity extends Activity implements ReaderView.Listener {
    private static final String TAG = "EXRHost";
    private static final int REQUEST_IMPORT = 1001;
    private static final long MAX_INPUT_BYTES = 32L * 1024 * 1024;
    private static final String PREFS = "host";
    private static final String DOWNLOADS_URI =
            "content://com.android.externalstorage.documents/document/primary%3ADownload";

    private static byte[] FONT;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private ExecutorService worker;
    private BookStore store;
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

    private final List<NativeLibrary.Book> books = new ArrayList<>();
    private final List<String> shelfRows = new ArrayList<>();
    private ArrayAdapter<String> shelfAdapter;
    private ArrayAdapter<String> noteAdapter;
    private List<?> shownNotes = new ArrayList<>();
    private final List<String> noteRows = new ArrayList<>();

    private NativeLibrary.Book currentBook;
    private ReflowSession reflow;
    private FixedSession fixed;
    private PageSnapshot current;
    private long generation;
    private boolean pageBusy;
    private volatile boolean importCancel;
    private volatile boolean openCancel;
    private volatile boolean destroyed;
    private int operation;

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
        super.onCreate(savedInstanceState);
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
        wireActions();
        readerView.setListener(this);

        worker = Executors.newSingleThreadExecutor(runnable -> {
            Thread thread = new Thread(runnable, "exr-host-worker");
            thread.setDaemon(true);
            return thread;
        });

        worker.execute(() -> {
            try {
                store = new BookStore(new File(getFilesDir(), "library.db"));
            } catch (Throwable error) {
                postStatus("Library error: " + message(error));
                return;
            }
            postUi(this::updateSdkLabel);
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

        shelfAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, shelfRows);
        bookList.setAdapter(shelfAdapter);
        noteAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, noteRows);
        noteList.setAdapter(noteAdapter);
        statusText.setContentDescription("Status");
    }

    private void wireActions() {
        importButton.setOnClickListener(view -> startImport());
        refreshButton.setOnClickListener(view -> {
            loadShelf(false);
            setStatus("Shelf refreshed");
        });
        rebuildView.setOnClickListener(view -> {
            saveInstancePrefs();
            recreate();
        });
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
            if (operation == 1) {
                importCancel = true;
                loadingText.setText("Canceling import...");
            } else if (operation == 2) {
                openCancel = true;
                loadingText.setText("Canceling open...");
            }
        });
        bookList.setOnItemClickListener((parent, view, position, id) -> {
            if (position < 0 || position >= books.size()) return;
            NativeLibrary.Book book = books.get(position);
            if (currentBook != null && currentBook.id == book.id && current != null) {
                showReader(book);
                return;
            }
            openBook(book.id, -1, -1);
        });
        noteList.setOnItemClickListener((parent, view, position, id) -> {
            if (position < 0 || position >= shownNotes.size()) return;
            Object note = shownNotes.get(position);
            hideNotes();
            navigateTo(note);
        });
        noteList.setOnItemLongClickListener((parent, view, position, id) -> {
            if (position < 0 || position >= shownNotes.size()) return true;
            Object note = shownNotes.get(position);
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
        worker.execute(() -> {
            List<NativeLibrary.Book> loaded;
            try {
                loaded = store == null ? new ArrayList<>() : store.books();
            } catch (Throwable error) {
                postStatus("Shelf error: " + message(error));
                return;
            }
            postUi(() -> {
                books.clear();
                books.addAll(loaded);
                shelfRows.clear();
                for (NativeLibrary.Book book : books) shelfRows.add(shelfRow(book));
                shelfAdapter.notifyDataSetChanged();
            });
            if (maybeOpen) {
                long target = restoreBook;
                if (target <= 0) target = prefs.getLong("lastBook", 0);
                boolean reader = restoreReader || prefs.getBoolean("lastReader", false);
                if (reader && target > 0) {
                    final long openId = target;
                    final long openOffset = restoreOffset;
                    final int openPage = restorePage;
                    postUi(() -> openBook(openId, openOffset, openPage));
                } else {
                    postUi(() -> showShelf(false));
                }
            }
        });
    }

    private String shelfRow(NativeLibrary.Book book) {
        long bytes = prefs.getLong("size_" + book.id, 0);
        String position = book.fixed() ? "page " + (book.position + 1) : "offset " + book.position;
        return book.title + "\n" + formatName(book.format) + " · " + humanBytes(bytes) + " · " + position;
    }

    private void openBook(long id, long offset, int page) {
        if (worker == null) return;
        if (store == null) {
            setStatus("Library is still opening");
            return;
        }
        NativeLibrary.Book book = null;
        for (NativeLibrary.Book candidate : books) if (candidate.id == id) book = candidate;
        if (book == null) {
            setStatus("Book is missing from the shelf");
            showShelf(false);
            return;
        }
        final NativeLibrary.Book target = book;
        final long gen = ++generation;
        operation = 2;
        openCancel = false;
        pageBusy = false;
        showLoading("Opening " + target.title + "...", true);
        final long requestedOffset = offset;
        final int requestedPage = page;
        worker.execute(() -> {
            String notice = null;
            try {
                closeSessionsLocked();
                String path = prefs.getString("path_" + target.id, null);
                if (path == null || !new File(path).isFile()) {
                    throw new IOException("The app-owned book copy is missing");
                }
                PageLoad load;
                if (target.fixed()) {
                    fixed = new FixedSession(path, fontBytes(), target.format);
                    int requested = requestedPage >= 0 ? requestedPage : (int) Math.max(0, target.position);
                    load = fixed.load(requested, zoom);
                } else {
                    reflow = new ReflowSession(path, fontBytes(), fontSize);
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
                    if (requestedOffset < 0 && state >= 0 && state != 1) {
                        notice = "Saved position is not exact (state " + state
                                + "); opened at stored offset " + seek + ".";
                    }
                    load = reflow.seek(seek);
                }
                if (load == null) throw new IllegalStateException("The book has no readable pages");
                Log.i(TAG, "handle open book=" + target.id + " mode=" + (target.fixed() ? "fixed" : "reflow"));
                if (openCancel) {
                    closeSessionsLocked();
                    postUi(() -> {
                        if (gen != generation) return;
                        operation = 0;
                        hideLoading();
                        setStatus("Open canceled");
                        showShelf(false);
                    });
                    return;
                }
                final PageLoad result = load;
                final String restored = notice;
                postUi(() -> {
                    if (gen != generation) return;
                    operation = 0;
                    hideLoading();
                    currentBook = target;
                    bookId = target.id;
                    prefs.edit().putLong("lastBook", target.id).putBoolean("lastReader", true).apply();
                    showReader(target);
                    setStatus("Opened " + target.title);
                    applyPage(gen, result, restored);
                    refreshNotesCount();
                });
            } catch (Throwable error) {
                closeSessionsLocked();
                final String detail = message(error);
                postUi(() -> {
                    if (gen != generation) return;
                    operation = 0;
                    hideLoading();
                    current = null;
                    readerView.setPage(null);
                    setStatus("Could not open " + target.title + ": " + detail);
                    showShelf(false);
                });
            }
        });
    }

    private void applyPage(long gen, PageLoad load, String notice) {
        if (gen != generation) return;
        current = load.snapshot;
        pageBusy = false;
        readerView.setPage(current);
        readerView.setSelectMode(false);
        selectButton.setText("Select");
        selectionBar.setVisibility(View.GONE);
        selectionStatus.setText("");
        bookTitle.setText(currentBook == null ? "" : currentBook.title);
        pageLabel.setText(pageSummary(load));
        fontLabel.setText("Size " + (int) fontSize);
        zoomLabel.setText(String.format(Locale.US, "Zoom %.2f", zoom));
        boolean isFixed = current.fixed;
        fontDown.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        fontUp.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        fontLabel.setVisibility(isFixed ? View.GONE : View.VISIBLE);
        zoomDown.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        zoomUp.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        zoomLabel.setVisibility(isFixed ? View.VISIBLE : View.GONE);
        if (notice != null) setStatus(notice);
        Log.i(TAG, "metric {\"event\":\"page\",\"book\":" + bookId + ",\"page\":" + (current.index + 1)
                + ",\"fixed\":" + isFixed + ",\"bytes\":" + current.bitmapBytes
                + ",\"ms\":" + load.millis + "}");
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
    }

    private void leaveReader() {
        final PageSnapshot snapshot = current;
        ++generation;
        pageBusy = false;
        current = null;
        readerView.setPage(null);
        readerPanel.setVisibility(View.GONE);
        notesPanel.setVisibility(View.GONE);
        shelfPanel.setVisibility(View.VISIBLE);
        selectionBar.setVisibility(View.GONE);
        prefs.edit().putBoolean("lastReader", false).apply();
        if (worker != null) {
            worker.execute(() -> {
                if (snapshot != null) saveProgressLocked(snapshot);
                closeSessionsLocked();
            });
        }
        loadShelf(false);
    }

    private void turnPage(int delta) {
        if (worker == null || current == null || pageBusy || operation != 0) return;
        final long gen = generation;
        pageBusy = true;
        worker.execute(() -> {
            try {
                PageLoad load;
                if (current.fixed) {
                    if (fixed == null) return;
                    load = fixed.load(fixed.index() + delta, zoom);
                } else {
                    if (reflow == null) return;
                    load = delta > 0 ? reflow.next() : reflow.previous();
                }
                if (load == null) {
                    postUi(() -> {
                        if (gen != generation) return;
                        pageBusy = false;
                        setStatus(delta > 0 ? "End of book" : "Start of book");
                    });
                    return;
                }
                saveProgressLocked(load.snapshot);
                postUi(() -> applyPage(gen, load, null));
            } catch (Throwable error) {
                postUi(() -> {
                    if (gen != generation) return;
                    pageBusy = false;
                    setStatus("Page error: " + message(error));
                });
            }
        });
    }

    private void changeFont(int direction) {
        if (worker == null || current == null || current.fixed || pageBusy || operation != 0) return;
        float size = Math.max(18f, Math.min(40f, fontSize + direction * 4f));
        if (size == fontSize) {
            setStatus("Font size limit");
            return;
        }
        fontSize = size;
        prefs.edit().putFloat("font", size).apply();
        final long gen = generation;
        pageBusy = true;
        worker.execute(() -> {
            try {
                PageLoad load = reflow.setFontSize(size);
                if (load == null) throw new IllegalStateException("The book has no readable pages");
                saveProgressLocked(load.snapshot);
                postUi(() -> {
                    if (gen != generation) return;
                    applyPage(gen, load, null);
                    setStatus("Font size " + (int) size);
                });
            } catch (Throwable error) {
                postUi(() -> {
                    if (gen != generation) return;
                    pageBusy = false;
                    setStatus("Layout error: " + message(error));
                });
            }
        });
    }

    private void changeZoom(int direction) {
        if (worker == null || current == null || !current.fixed || pageBusy || operation != 0) return;
        float next = Math.max(1.0f, Math.min(2.0f, zoom + direction * 0.25f));
        if (next == zoom) {
            setStatus("Zoom limit");
            return;
        }
        zoom = next;
        prefs.edit().putFloat("zoom", next).apply();
        final long gen = generation;
        pageBusy = true;
        worker.execute(() -> {
            try {
                PageLoad load = fixed.load(fixed.index(), zoom);
                postUi(() -> {
                    if (gen != generation) return;
                    applyPage(gen, load, null);
                    setStatus(String.format(Locale.US, "Zoom %.2f", zoom));
                });
            } catch (Throwable error) {
                postUi(() -> {
                    if (gen != generation) return;
                    pageBusy = false;
                    setStatus("Zoom error: " + message(error));
                });
            }
        });
    }

    private void saveProgressLocked(PageSnapshot snapshot) {
        if (store == null || snapshot == null || bookId <= 0) return;
        try {
            if (snapshot.fixed) {
                store.setPosition(bookId, snapshot.index);
            } else {
                store.saveProgress(bookId, snapshot.start);
                store.setPosition(bookId, snapshot.start);
            }
        } catch (Throwable error) {
            Log.w(TAG, "progress save failed: " + message(error));
        }
    }

    private void closeSessionsLocked() {
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
        if (closed) Log.i(TAG, "handle close book=" + bookId);
    }

    private void refreshNotesCount() {
        if (worker == null || currentBook == null) return;
        final NativeLibrary.Book book = currentBook;
        worker.execute(() -> {
            int count = 0;
            try {
                count = book.fixed() ? store.fixedNotes(book.id).size() : store.notes(book.id).size();
            } catch (Throwable error) {
                Log.w(TAG, "annotation count failed: " + message(error));
            }
            final int value = count;
            postUi(() -> notesButton.setText("Notes (" + value + ")"));
        });
    }

    private void showNotes() {
        if (worker == null || currentBook == null) return;
        final NativeLibrary.Book book = currentBook;
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
                postUi(() -> showNotesPanel(rows, notes));
            } catch (Throwable error) {
                postStatus("Annotation list error: " + message(error));
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
        if (worker == null || current == null) return;
        final long gen = generation;
        pageBusy = true;
        worker.execute(() -> {
            try {
                PageLoad load;
                if (note instanceof NativeLibrary.FixedNote) {
                    NativeLibrary.FixedNote fixedNote = (NativeLibrary.FixedNote) note;
                    if (fixed == null) throw new IllegalStateException("The fixed reader is closed");
                    load = fixed.load((int) fixedNote.page, zoom);
                } else {
                    NativeLibrary.Note reflowNote = (NativeLibrary.Note) note;
                    if (reflowNote.start < 0) {
                        postUi(() -> {
                            if (gen == generation) {
                                pageBusy = false;
                                setStatus("Annotation range is unresolved");
                            }
                        });
                        return;
                    }
                    load = reflow.seek(reflowNote.start);
                }
                postUi(() -> {
                    if (gen != generation) return;
                    applyPage(gen, load, null);
                    setStatus("Jumped to annotation");
                });
            } catch (Throwable error) {
                postUi(() -> {
                    if (gen != generation) return;
                    pageBusy = false;
                    setStatus("Annotation navigation error: " + message(error));
                });
            }
        });
    }

    private void copySelection() {
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
        String comment = raw == null ? "" : raw.trim();
        if (comment.isEmpty()) comment = ReaderView.clip(pendingSelected, 80);
        if (comment.isEmpty()) comment = "(no comment)";
        final String text = comment;
        if (worker == null) return;
        if (noteId > 0) {
            worker.execute(() -> {
                try {
                    if (pendingFixed) {
                        store.saveFixedNote(bookId, noteId, pendingPage, pendingStart, pendingEnd, text);
                    } else {
                        store.updateNoteText(noteId, text);
                    }
                    postStatus("Annotation updated");
                    refreshNotesCount();
                    postUi(() -> {
                        if (notesPanel.getVisibility() == View.VISIBLE) showNotes();
                    });
                } catch (Throwable error) {
                    postStatus("Could not update annotation: " + message(error));
                }
            });
            return;
        }
        final boolean isFixed = current != null && current.fixed;
        final long start = pendingStart;
        final long end = pendingEnd;
        final int page = pendingPage;
        worker.execute(() -> {
            try {
                if (isFixed) {
                    store.saveFixedNote(bookId, 0, page, start, end, text);
                } else {
                    store.saveNote(bookId, 0, start, end, text);
                }
                postStatus("Annotation saved");
                refreshNotesCount();
            } catch (Throwable error) {
                postStatus("Could not save annotation: " + message(error));
            }
        });
    }

    private void deleteNote(long noteId) {
        if (worker == null) return;
        final boolean isFixed = current != null && current.fixed;
        worker.execute(() -> {
            try {
                if (isFixed) store.removeFixedNote(noteId);
                else store.removeNote(noteId);
                postUi(() -> {
                    setStatus("Annotation deleted");
                    hideNotes();
                });
                refreshNotesCount();
            } catch (Throwable error) {
                postStatus("Could not delete annotation: " + message(error));
            }
        });
    }

    private void startImport() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
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
        if (resultCode != RESULT_OK || data == null || data.getData() == null) {
            setStatus("Selection canceled");
            return;
        }
        Uri uri = data.getData();
        try {
            getContentResolver().takePersistableUriPermission(uri,
                    data.getFlags() & Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch (Exception ignored) {
            // The app copies the source immediately, so a denied grant is not fatal.
        }
        String name = queryName(uri);
        long size = querySize(uri);
        int format = formatFor(name);
        if (format < 0) {
            setStatus("Unsupported format: " + name);
            return;
        }
        if (size > MAX_INPUT_BYTES) {
            setStatus("File exceeds 32 MiB limit: " + name);
            return;
        }
        importUri(uri, name, format);
    }

    private void importUri(Uri uri, String name, int format) {
        if (worker == null) return;
        operation = 1;
        importCancel = false;
        showLoading("Importing " + name + "...", true);
        worker.execute(() -> {
            File copied = null;
            long importedId = 0;
            boolean created = false;
            try {
                copied = copyUri(uri, name);
                if (importCancel) throw new CancelledImport();
                String path = copied.getAbsolutePath();
                if (format == NativeLibrary.FORMAT_PDF) {
                    byte[] bytes = readFile(copied);
                    EXReader.FixedDocument document = new EXReader.Pdf(bytes, fontBytes(), 0);
                    document.close();
                } else if (format == NativeLibrary.FORMAT_CBZ) {
                    byte[] bytes = readFile(copied);
                    EXReader.FixedDocument document = new EXReader.FixedDocument(EXReader.FixedFormat.CBZ, bytes);
                    document.close();
                } else {
                    EXReader.Document document = new EXReader.Document(path);
                    document.close();
                }
                if (importCancel) throw new CancelledImport();
                NativeLibrary.ImportResult result = store.importFile(path, format, name);
                importedId = result.id;
                created = result.created;
                if (importCancel) {
                    if (created) store.deleteBook(importedId);
                    throw new CancelledImport();
                }
                prefs.edit().putString("path_" + importedId, path)
                        .putLong("size_" + importedId, copied.length()).apply();
                final boolean inserted = created;
                postUi(() -> {
                    operation = 0;
                    hideLoading();
                    setStatus(inserted ? "Imported " + name : "Already in shelf: " + name);
                    loadShelf(false);
                });
            } catch (CancelledImport canceled) {
                if (copied != null) copied.delete();
                if (importedId > 0 && created) {
                    try { store.deleteBook(importedId); } catch (Throwable ignored) { }
                }
                postUi(() -> {
                    operation = 0;
                    hideLoading();
                    setStatus("Import canceled");
                    loadShelf(false);
                });
            } catch (Throwable error) {
                if (copied != null) copied.delete();
                if (importedId > 0 && created) {
                    try { store.deleteBook(importedId); } catch (Throwable ignored) { }
                }
                final String detail = message(error);
                postUi(() -> {
                    operation = 0;
                    hideLoading();
                    setStatus("Could not open " + name + ": " + detail);
                    loadShelf(false);
                });
            }
        });
    }

    private File copyUri(Uri uri, String name) throws IOException {
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
             OutputStream output = new FileOutputStream(temporary)) {
            if (input == null) throw new IOException("The picker returned an unreadable source");
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) > 0) {
                if (importCancel) throw new CancelledImport();
                total += count;
                if (total > MAX_INPUT_BYTES) throw new IOException("File exceeds 32 MiB limit");
                output.write(buffer, 0, count);
                digest.update(buffer, 0, count);
            }
        } catch (CancelledImport canceled) {
            temporary.delete();
            throw canceled;
        } catch (Throwable error) {
            temporary.delete();
            if (error instanceof IOException) throw (IOException) error;
            throw new IOException(message(error));
        }
        if (total == 0) {
            temporary.delete();
            throw new IOException("The selected file is empty");
        }
        String extension = extension(name);
        File target = new File(folder, hex(digest.digest()) + (extension.isEmpty() ? "" : "." + extension));
        if (target.isFile()) {
            temporary.delete();
        } else if (!temporary.renameTo(target)) {
            temporary.delete();
            throw new IOException("Cannot keep the app-owned copy");
        }
        return target;
    }

    private static final class CancelledImport extends IOException {
        CancelledImport() { super("Import canceled"); }
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
        super.onStop();
        saveInstancePrefs();
        final PageSnapshot snapshot = current;
        if (worker != null && snapshot != null) {
            worker.execute(() -> saveProgressLocked(snapshot));
        }
    }

    @Override public void onBackPressed() {
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
        destroyed = true;
        ++generation;
        final ExecutorService service = worker;
        worker = null;
        final PageSnapshot snapshot = current;
        final BookStore openStore = store;
        if (service != null) {
            service.execute(() -> {
                try {
                    saveProgressLocked(snapshot);
                    closeSessionsLocked();
                    if (openStore != null) openStore.close();
                } catch (Throwable error) {
                    Log.w(TAG, "shutdown failed: " + message(error));
                }
            });
            service.shutdown();
            try {
                service.awaitTermination(2, TimeUnit.SECONDS);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        }
        super.onDestroy();
    }

    @Override public void onTapZone(int delta) {
        turnPage(delta);
    }

    @Override public void onSelectionChanged(Selection selection) {
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
