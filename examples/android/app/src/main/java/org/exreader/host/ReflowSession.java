// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;

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

    ReflowSession(String path, byte[] font, float size) {
        this.font = font;
        this.fontSize = size;
        document = new EXReader.Document(path);
        text = document.utf8();
        title = document.title();
        resetPager();
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

    private void resetPager() {
        if (pager != null) pager.close();
        pager = document.pager(font, 0, config(fontSize));
        index = -1;
        atEnd = false;
    }

    PageLoad next() {
        if (closed || atEnd) return null;
        return readPage();
    }

    PageLoad previous() {
        if (closed || index <= 0) return null;
        return seekToIndex(index - 1);
    }

    PageLoad seek(long offset) {
        if (closed) return null;
        if (offset < 0) offset = 0;
        resetPager();
        PageLoad last = null;
        int guard = 0;
        while (guard++ < 20000) {
            PageLoad load = readPage();
            if (load == null) return last;
            last = load;
            if (load.snapshot.end > offset || load.snapshot.start >= offset) return load;
        }
        return last;
    }

    PageLoad seekToIndex(int target) {
        if (closed) return null;
        if (target < 0) target = 0;
        resetPager();
        PageLoad last = null;
        int guard = 0;
        while (guard++ <= target + 1) {
            PageLoad load = readPage();
            if (load == null) return last;
            last = load;
            if (index >= target) return load;
        }
        return last;
    }

    PageLoad setFontSize(float size) {
        long keep = 0;
        if (index >= 0) {
            // The current page start is not retained after readPage; use the
            // last offset stored by the caller through seek().
            keep = lastStart;
        }
        fontSize = size;
        return seek(keep);
    }

    private long lastStart = 0;

    private PageLoad readPage() {
        long started = System.nanoTime();
        EXReader.ReflowPage page = null;
        try {
            page = pager.next();
            if (page == null) {
                atEnd = true;
                return null;
            }
            index++;
            EXReader.LayoutSnapshot layout = page.snapshot();
            EXReader.Bitmap nativeBitmap = page.render();
            if (nativeBitmap == null) throw new IllegalStateException("No page bitmap");
            Bitmap bitmap = toBitmap(nativeBitmap);
            PageSnapshot snapshot = build(layout, bitmap);
            lastStart = snapshot.start;
            return new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L);
        } finally {
            if (page != null) page.close();
        }
    }

    private PageSnapshot build(EXReader.LayoutSnapshot layout, Bitmap bitmap) {
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
        return new PageSnapshot(bitmap, false, index, -1, start, end, text, 1f,
                bitmap.getWidth(), bitmap.getHeight(), starts, ends, null,
                gx, baseline, advance, size, lineText, lineBounds, 0);
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
