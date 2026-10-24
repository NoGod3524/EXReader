// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.util.AttributeSet;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.TextView;

/** Ordinary status text with bounded debug observations, matching the host's reader observations. */
public final class ShelfStatusView extends TextView {
    private CatalogShelf shelf;
    public ShelfStatusView(Context context,AttributeSet attributes) { super(context,attributes); }
    void bind(CatalogShelf shelf) { this.shelf=shelf; }
    @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
        super.onInitializeAccessibilityNodeInfo(info);
        if (BuildConfig.DEBUG && shelf!=null) info.getExtras().putString("exreader.shelf",shelf.observation());
    }
}
