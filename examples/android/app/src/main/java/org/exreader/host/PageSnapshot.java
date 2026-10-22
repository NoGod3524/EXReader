// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.Bitmap;
import android.graphics.RectF;

/** Immutable UI-side page: bitmap, engine geometry and text for selection. */
final class PageSnapshot {
    boolean bounded;
    int part = -1;
    String path;
    long textBase, boundedHandle;
    boolean preserveProgress;
    String restoreNotice;
    long highlightStart=-1, highlightEnd=-1;
    BoundedEpub boundedOwner;
    String[] boundedLocation;
    float layoutFont;
    final long bookId;
    final Bitmap bitmap;
    final boolean fixed;
    final int index;
    final int pageCount;
    final long start;
    final long end;
    final byte[] text;
    final float renderScale;
    final float contentWidth;
    final float contentHeight;
    final long[] starts;
    final long[] ends;
    final float[][] quads;
    final float[] glyphX;
    final float[] glyphBaseline;
    final float[] glyphAdvance;
    final float[] glyphSize;
    final String[] lineText;
    final RectF[] lineBounds;
    final long millis;
    final long bitmapBytes;

    PageSnapshot(Bitmap bitmap, boolean fixed, int index, int pageCount, long start, long end,
                 byte[] text, float renderScale, float contentWidth, float contentHeight,
                 long[] starts, long[] ends, float[][] quads,
                 float[] glyphX, float[] glyphBaseline, float[] glyphAdvance, float[] glyphSize,
                 String[] lineText, RectF[] lineBounds, long millis, long bookId) {
        this.bookId = bookId;
        this.bitmap = bitmap;
        this.fixed = fixed;
        this.index = index;
        this.pageCount = pageCount;
        this.start = start;
        this.end = end;
        this.text = text;
        this.renderScale = renderScale;
        this.contentWidth = contentWidth;
        this.contentHeight = contentHeight;
        this.starts = starts;
        this.ends = ends;
        this.quads = quads;
        this.glyphX = glyphX;
        this.glyphBaseline = glyphBaseline;
        this.glyphAdvance = glyphAdvance;
        this.glyphSize = glyphSize;
        this.lineText = lineText;
        this.lineBounds = lineBounds;
        this.millis = millis;
        this.bitmapBytes = bitmap == null ? 0 : (long) bitmap.getWidth() * bitmap.getHeight() * 4L;
    }

    int glyphCount() {
        return starts == null ? 0 : starts.length;
    }

    int regionCount() {
        return quads == null ? 0 : quads.length;
    }
}
