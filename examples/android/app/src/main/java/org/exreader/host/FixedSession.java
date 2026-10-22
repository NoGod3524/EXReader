// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;

import org.exreader.EXReader;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * Fixed-page reader state. The whole fixed document is opened from the app-owned
 * copy; each page render is independent and the bitmap outlives document close.
 */
final class FixedSession implements AutoCloseable {
    private final EXReader.FixedDocument document;
    private final int pageCount;
    private final float baseScale;
    private int index;
    private boolean closed;

    FixedSession(String path, byte[] font, int format) throws IOException {
        byte[] bytes = read(path);
        if (format == NativeLibrary.FORMAT_CBZ) {
            document = new EXReader.FixedDocument(EXReader.FixedFormat.CBZ, bytes);
        } else {
            document = new EXReader.Pdf(bytes, font, 0);
        }
        pageCount = document.pageCount();
        if (pageCount <= 0) throw new IllegalStateException("The document has no pages");
        EXReader.Bitmap probe = document.render(0, 1.0);
        if (probe == null || probe.width <= 0) throw new IllegalStateException("The first page cannot be rendered");
        baseScale = Math.max(0.25f, Math.min(20f, 600f / probe.width));
    }

    int pageCount() {
        return pageCount;
    }

    int index() {
        return index;
    }

    PageLoad load(int page, float zoom) {
        if (closed) return null;
        if (page < 0) page = 0;
        if (page >= pageCount) page = pageCount - 1;
        index = page;
        long started = System.nanoTime();
        float scale = baseScale * zoom;
        EXReader.Bitmap nativeBitmap = document.render(page, scale);
        if (nativeBitmap == null) throw new IllegalStateException("No page bitmap");
        Bitmap bitmap = ReflowSession.toBitmap(nativeBitmap);
        EXReader.TextPage textPage = null;
        try {
            textPage = document.text(page);
        } catch (RuntimeException ignored) {
            // A page without a text layer is still a valid fixed page.
        }
        byte[] text = textPage == null || textPage.utf8 == null ? new byte[0] : textPage.utf8;
        int regions = textPage == null ? 0 : textPage.flags.length;
        long[] starts = new long[regions];
        long[] ends = new long[regions];
        float[][] quads = new float[regions][8];
        for (int i = 0; i < regions; i++) {
            starts[i] = textPage.ranges[i * 2];
            ends[i] = textPage.ranges[i * 2 + 1];
            for (int k = 0; k < 8; k++) quads[i][k] = (float) textPage.quads[i * 8 + k];
        }
        String[] lineText;
        RectF[] lineBounds;
        LineSet lines = buildLines(text, starts, ends, quads, textPage == null ? null : textPage.flags);
        lineText = lines.text;
        lineBounds = lines.bounds;
        float contentWidth = bitmap.getWidth() / scale;
        float contentHeight = bitmap.getHeight() / scale;
        PageSnapshot snapshot = new PageSnapshot(bitmap, true, page, pageCount, 0, text.length,
                text, scale, contentWidth, contentHeight, starts, ends, quads,
                null, null, null, null, lineText, lineBounds, 0);
        return new PageLoad(snapshot, (System.nanoTime() - started) / 1000000L);
    }

    private static final class LineSet {
        final String[] text;
        final RectF[] bounds;

        LineSet(String[] text, RectF[] bounds) {
            this.text = text;
            this.bounds = bounds;
        }
    }

    private static LineSet buildLines(byte[] pageText, long[] starts, long[] ends,
                                      float[][] quads, int[] flags) {
        java.util.List<StringBuilder> texts = new java.util.ArrayList<>();
        java.util.List<RectF> boxes = new java.util.ArrayList<>();
        java.util.List<Float> centers = new java.util.ArrayList<>();
        for (int i = 0; i < quads.length; i++) {
            if (flags != null && (flags[i] & 2) != 0) continue;
            RectF box = box(quads[i]);
            if (box.width() <= 0 || box.height() <= 0) continue;
            String value = ReflowSession.slice(pageText, starts[i], ends[i]);
            if (value.isEmpty()) continue;
            int group = -1;
            for (int g = 0; g < centers.size(); g++) {
                float tolerance = Math.max(box.height(), boxes.get(g).height()) * 0.6f;
                if (Math.abs(box.centerY() - centers.get(g)) <= tolerance) {
                    group = g;
                    break;
                }
            }
            if (group < 0) {
                texts.add(new StringBuilder(value));
                boxes.add(new RectF(box));
                centers.add(box.centerY());
            } else {
                RectF current = boxes.get(group);
                StringBuilder builder = texts.get(group);
                if (box.left - current.right > Math.max(2f, box.height() * 0.2f)) builder.append(' ');
                builder.append(value);
                current.union(box);
                centers.set(group, current.centerY());
            }
        }
        String[] text = new String[texts.size()];
        RectF[] bounds = new RectF[texts.size()];
        for (int i = 0; i < text.length; i++) {
            text[i] = texts.get(i).toString().trim();
            bounds[i] = boxes.get(i);
        }
        return new LineSet(text, bounds);
    }

    private static RectF box(float[] quad) {
        float left = Math.min(Math.min(quad[0], quad[2]), Math.min(quad[4], quad[6]));
        float top = Math.min(Math.min(quad[1], quad[3]), Math.min(quad[5], quad[7]));
        float right = Math.max(Math.max(quad[0], quad[2]), Math.max(quad[4], quad[6]));
        float bottom = Math.max(Math.max(quad[1], quad[3]), Math.max(quad[5], quad[7]));
        return new RectF(left, top, right, bottom);
    }

    private static byte[] read(String path) throws IOException {
        File file = new File(path);
        if (file.length() > 32L * 1024 * 1024) throw new IOException("File exceeds 32 MiB");
        ByteArrayOutputStream out = new ByteArrayOutputStream((int) Math.max(1024, file.length()));
        FileInputStream in = new FileInputStream(file);
        try {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = in.read(buffer)) > 0) out.write(buffer, 0, count);
        } finally {
            in.close();
        }
        return out.toByteArray();
    }

    @Override
    public void close() {
        if (closed) return;
        closed = true;
        document.close();
    }
}
