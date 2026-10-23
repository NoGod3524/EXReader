// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.graphics.RectF;
import java.util.List;

/** A committed text selection in page content coordinates. */
final class Selection {
    final int pageIndex;
    final long start;
    final long end;
    final String text;
    final List<RectF> rects;

    Selection(int pageIndex, long start, long end, String text, List<RectF> rects) {
        this.pageIndex = pageIndex;
        this.start = start;
        this.end = end;
        this.text = text;
        this.rects = rects;
    }
}
