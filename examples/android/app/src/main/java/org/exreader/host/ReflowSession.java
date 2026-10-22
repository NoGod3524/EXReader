// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;
import android.util.Log;

import org.exreader.EXReader;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

/**
 * Reflow reader state. Owned by the host worker thread: the document, pager and
 * font are opened and released on that thread only. Pages are rendered to an
 * owned bitmap and the native page handle is closed before returning.
 */
final class ReflowSession implements AutoCloseable {
    static final float PAGE_WIDTH = 600f;
    static final float PAGE_HEIGHT = 860f;
    static final float MARGIN = 32f;

    private final EXReader.Document document;
    private final byte[] text;
    private final byte[] font;
    private EXReader.Pager pager;
    private float fontSize;
    private int index = -1;
    private boolean atEnd;
    private boolean closed;
    private final String title;
    private final long bookId;
    private long nativeNextCalls;
    private long recoveryCalls;

    ReflowSession(long bookId, String path, byte[] font, float size) {
        this.bookId = bookId;
        this.font = font;
        this.fontSize = size;
        document = new EXReader.Document(path);
        try {
            text = document.utf8();
            title = document.title();
        } catch (RuntimeException | Error error) { document.close(); throw error; }
    }

    String title() {
        return title;
    }

    byte[] text() {
        return text;
    }

    int index() {
        return index;
    }

    float fontSize() {
        return fontSize;
    }

    private EXReader.LayoutConfig config(float size) {
        EXReader.LayoutConfig config = new EXReader.LayoutConfig();
        config.width = PAGE_WIDTH;
        config.height = PAGE_HEIGHT;
        config.margin = MARGIN;
        config.fontSize = size;
        config.lineHeight = 1.6f;
        config.paragraphSpacing = 12f;
        config.documentCSS = true;
        config.embeddedFonts = true;
        config.direction = 0;
        return config;
    }

    PageLoad next(HostTask task) throws Exception {
        if (pager == null) return prepare(index + 1, -1, fontSize, task);
        task.check();
        long started = System.nanoTime();
        try (EXReader.ReflowPage page = nextPage(pager, false)) {
            if (page == null) return null;
            EXReader.LayoutSnapshot layout = page.snapshot();
            task.check();
            EXReader.Bitmap rendered = page.render();
            task.check();
            if (rendered == null) throw new IllegalStateException("No page bitmap");
            PageSnapshot snapshot = build(layout, toBitmap(rendered), index + 1);
            return new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L,
                    () -> { index = snapshot.index; lastStart = snapshot.start; logSteps(); },
                    this::recoverAcceptedCursor);
        } catch (Exception | Error error) { recoverAcceptedCursor(); throw error; }
    }

    private EXReader.ReflowPage nextPage(EXReader.Pager source, boolean recovery) {
        nativeNextCalls++;
        if (recovery) recoveryCalls++;
        return source.next();
    }

    private void logSteps() {
        Log.i("EXRHost", "paging {\"book\":" + bookId + ",\"index\":" + index +
                ",\"native_next_calls\":" + nativeNextCalls + ",\"recovery_calls\":" + recoveryCalls + "}");
    }

    private void recoverAcceptedCursor() {
        if (pager != null) pager.close();
        pager = null;
        if (closed) return;
        EXReader.Pager restored = null;
        try {
            restored = document.pager(font, 0, config(fontSize));
            if (index >= 20000) throw new IllegalStateException("Recovery exceeds the host page budget");
            for (int at = 0; at <= index; at++) {
                try (EXReader.ReflowPage page = nextPage(restored, true)) {
                    if (page == null) throw new IllegalStateException("Accepted page no longer exists");
                }
            }
            pager = restored;
            restored = null;
        } catch (RuntimeException error) {
            Log.w("EXRHost", "Cursor recovery failed; next request must rebuild: " + error.getMessage());
        } finally { if (restored != null) restored.close(); }
    }
    PageLoad previous(HostTask task) throws Exception {
        return index <= 0 ? null : prepare(index - 1, -1, fontSize, task);
    }
    PageLoad seek(long offset, HostTask task) throws Exception {
        if (offset < 0 || offset > text.length) throw new IllegalArgumentException("Text position is outside the document");
        return prepare(-1, offset, fontSize, task);
    }
    PageLoad setFontSize(float size, HostTask task) throws Exception { return prepare(-1, lastStart, size, task); }

    private long lastStart = 0;

    private PageLoad prepare(int target, long offset, float size, HostTask task) throws Exception {
        if (closed) throw new IllegalStateException("Reader is closed");
        task.check();
        long started = System.nanoTime();
        final EXReader.Pager candidate = document.pager(font, 0, config(size));
        boolean transferred = false;
        try {
            // The installed Java binding exposes sequential pagers. Replay an
            // independent candidate so a render/database failure cannot advance
            // the accepted cursor. Preceding pages are not rasterized.
            for (int at = 0; at < 20000; at++) {
                task.check();
                try (EXReader.ReflowPage page = nextPage(candidate, false)) {
                    if (page == null) {
                        if (target >= 0) return null;
                        throw new IllegalArgumentException("No page contains the requested text position");
                    }
                    EXReader.LayoutSnapshot layout = page.snapshot();
                    boolean contains = offset >= layout.start && (offset < layout.end ||
                            (offset == text.length && layout.end == offset));
                    if (target >= 0 ? at != target : !contains) continue;
                    task.check();
                    EXReader.Bitmap rendered = page.render();
                    task.check();
                    if (rendered == null) throw new IllegalStateException("No page bitmap");
                    Bitmap bitmap = toBitmap(rendered);
                    final int acceptedIndex = at;
                    PageSnapshot snapshot = build(layout, bitmap, at);
                    PageLoad result = new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L,
                            () -> {
                                if (pager != null) pager.close();
                                pager = candidate;
                                index = acceptedIndex;
                                fontSize = size;
                                lastStart = snapshot.start;
                                logSteps();
                            }, candidate::close);
                    transferred = true;
                    return result;
                }
            }
            throw new IllegalStateException("Seek exceeds the 20000-page host budget");
        } finally { if (!transferred) candidate.close(); }
    }

    private PageSnapshot build(EXReader.LayoutSnapshot layout, Bitmap bitmap, int pageIndex) {
        try { return buildSnapshot(layout, bitmap, pageIndex); }
        catch (RuntimeException | Error error) { bitmap.recycle(); throw error; }
    }

    private PageSnapshot buildSnapshot(EXReader.LayoutSnapshot layout, Bitmap bitmap, int pageIndex) {
        int glyphCount = layout.glyphs.length;
        long[] starts = new long[glyphCount];
        long[] ends = new long[glyphCount];
        float[] gx = new float[glyphCount];
        float[] baseline = new float[glyphCount];
        float[] advance = new float[glyphCount];
        float[] size = new float[glyphCount];
        for (int i = 0; i < glyphCount; i++) {
            EXReader.Glyph glyph = layout.glyphs[i];
            starts[i] = glyph.start;
            ends[i] = glyph.end;
            gx[i] = glyph.x;
            baseline[i] = glyph.baseline;
            advance[i] = glyph.advance;
            size[i] = glyph.size;
        }
        int lineCount = layout.lines.length;
        String[] lineText = new String[lineCount];
        RectF[] lineBounds = new RectF[lineCount];
        for (int i = 0; i < lineCount; i++) {
            EXReader.Line line = layout.lines[i];
            lineText[i] = slice(text, line.start, line.end).trim();
            lineBounds[i] = new RectF(line.x, line.y, line.x + line.width, line.y + line.height);
        }
        long start = layout.start == -1 ? 0 : layout.start;
        long end = layout.end == -1 ? text.length : layout.end;
        return new PageSnapshot(bitmap, false, pageIndex, -1, start, end, text, 1f,
                bitmap.getWidth(), bitmap.getHeight(), starts, ends, null,
                gx, baseline, advance, size, lineText, lineBounds, 0, bookId);
    }

    static Bitmap toBitmap(EXReader.Bitmap source) {
        Bitmap bitmap = Bitmap.createBitmap(source.width, source.height, Bitmap.Config.ARGB_8888);
        int row = source.width * 4;
        if (source.stride != row) {
            byte[] packed = new byte[row * source.height];
            for (int y = 0; y < source.height; y++) {
                System.arraycopy(source.pixels, y * source.stride, packed, y * row, row);
            }
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(packed));
        } else {
            bitmap.copyPixelsFromBuffer(ByteBuffer.wrap(source.pixels));
        }
        return bitmap;
    }

    static String slice(byte[] bytes, long start, long end) {
        if (bytes == null || start < 0 || end < start || end > bytes.length) return "";
        return new String(bytes, (int) start, (int) (end - start), StandardCharsets.UTF_8);
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        if (pager != null) {
            pager.close();
            pager = null;
        }
        document.close();
    }
}
