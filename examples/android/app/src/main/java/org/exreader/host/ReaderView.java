// SPDX-License-Identifier: MIT
package org.exreader.host;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.RectF;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.AttributeSet;
import android.view.MotionEvent;
import android.view.View;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityNodeProvider;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Renders engine page bitmaps, maps touches back to engine glyph/region
 * coordinates, and exposes one virtual accessibility node per text line.
 */
public final class ReaderView extends View {
    public interface Listener {
        void onTapZone(int delta);
        void onSelectionChanged(Selection selection);
        void onSelectionCleared();
        void onSelectModeChanged(boolean enabled);
    }

    private static final int LONG_PRESS_MS = 450;

    private final Paint bitmapPaint = new Paint(Paint.FILTER_BITMAP_FLAG | Paint.DITHER_FLAG);
    private final Paint selectionPaint = new Paint();
    private final Paint handlePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint emptyPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Handler handler = new Handler(Looper.getMainLooper());

    private PageSnapshot page;
    private Listener listener;
    private boolean selectMode;
    private Selection selection;
    private int anchor = -1;
    private int focus = -1;
    private float fit = 1f;
    private float offsetX;
    private float offsetY;
    private boolean down;
    private boolean moved;
    private boolean longPress;
    private float downX;
    private float downY;

    private String[] lineText = new String[0];
    private RectF[] lineBounds = new RectF[0];
    private int accessibilityFocused = -1;

    private final Runnable longPressRunnable = new Runnable() {
        @Override public void run() {
            if (!down || moved || selectMode || page == null) return;
            longPress = true;
            setSelectMode(true);
            int hit = hit(downX, downY);
            if (hit >= 0) {
                anchor = hit;
                focus = hit;
                updateSelection(true);
            }
            if (listener != null) listener.onSelectModeChanged(true);
        }
    };

    private final AccessibilityNodeProvider provider = new AccessibilityNodeProvider() {
        @Override public AccessibilityNodeInfo createAccessibilityNodeInfo(int virtualViewId) {
            if (virtualViewId == HOST_VIEW_ID) return hostNode();
            if (virtualViewId < 1 || virtualViewId > lineText.length) return null;
            int index = virtualViewId - 1;
            AccessibilityNodeInfo info = AccessibilityNodeInfo.obtain(ReaderView.this, virtualViewId);
            info.setParent(ReaderView.this);
            info.setPackageName(getContext().getPackageName());
            info.setClassName("android.widget.TextView");
            info.setText(lineText[index]);
            info.setContentDescription(lineText[index]);
            info.setBoundsInScreen(screenBounds(lineBounds[index]));
            info.setVisibleToUser(true);
            info.setEnabled(true);
            info.setFocusable(true);
            info.setClickable(false);
            if (accessibilityFocused == virtualViewId) {
                info.setAccessibilityFocused(true);
                info.addAction(AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS);
            } else {
                info.addAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS);
            }
            return info;
        }

        @Override public List<AccessibilityNodeInfo> findAccessibilityNodeInfosByText(String text, int virtualViewId) {
            if (text == null) return Collections.emptyList();
            List<AccessibilityNodeInfo> result = new ArrayList<>();
            String needle = text.toLowerCase(java.util.Locale.ROOT);
            for (int i = 0; i < lineText.length; i++) {
                String value = lineText[i];
                if (value == null) continue;
                if (value.toLowerCase(java.util.Locale.ROOT).contains(needle)) {
                    AccessibilityNodeInfo info = createAccessibilityNodeInfo(i + 1);
                    if (info != null) result.add(info);
                }
            }
            return result;
        }

        @Override public boolean performAction(int virtualViewId, int action, Bundle arguments) {
            if (virtualViewId == HOST_VIEW_ID) return performAccessibilityAction(action, arguments);
            if (virtualViewId < 1 || virtualViewId > lineText.length) return false;
            if (action == AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS) {
                accessibilityFocused = virtualViewId;
                invalidate();
                sendAccessibilityEvent(AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED);
                return true;
            }
            if (action == AccessibilityNodeInfo.ACTION_CLEAR_ACCESSIBILITY_FOCUS) {
                if (accessibilityFocused == virtualViewId) accessibilityFocused = -1;
                sendAccessibilityEvent(AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUS_CLEARED);
                return true;
            }
            return false;
        }
    };

    public ReaderView(Context context) {
        super(context);
        init();
    }

    public ReaderView(Context context, AttributeSet attributes) {
        super(context, attributes);
        init();
    }

    public ReaderView(Context context, AttributeSet attributes, int style) {
        super(context, attributes, style);
        init();
    }

    private void init() {
        setFocusable(true);
        setClickable(true);
        setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
        selectionPaint.setColor(Color.argb(80, 21, 101, 192));
        handlePaint.setColor(Color.rgb(21, 101, 192));
        emptyPaint.setColor(Color.rgb(96, 96, 96));
        emptyPaint.setTextSize(30f);
        setContentDescription("Reading page");
    }

    public void setListener(Listener listener) {
        this.listener = listener;
    }

    public void setPage(PageSnapshot snapshot) {
        page = snapshot;
        selection = null;
        anchor = -1;
        focus = -1;
        accessibilityFocused = -1;
        if (snapshot == null) {
            lineText = new String[0];
            lineBounds = new RectF[0];
        } else {
            lineText = snapshot.lineText == null ? new String[0] : snapshot.lineText;
            lineBounds = snapshot.lineBounds == null ? new RectF[0] : snapshot.lineBounds;
        }
        setContentDescription(describe());
        invalidate();
        if (isShown()) sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
    }

    public PageSnapshot page() {
        return page;
    }

    public boolean isSelectMode() {
        return selectMode;
    }

    public void setSelectMode(boolean enabled) {
        if (selectMode == enabled) return;
        selectMode = enabled;
        if (!enabled) {
            selection = null;
            anchor = -1;
            focus = -1;
            invalidate();
            if (listener != null) listener.onSelectionCleared();
        }
        setContentDescription(describe());
        if (listener != null) listener.onSelectModeChanged(enabled);
    }

    public Selection getSelection() {
        return selection;
    }

    public void clearSelection() {
        selection = null;
        anchor = -1;
        focus = -1;
        invalidate();
        if (listener != null) listener.onSelectionCleared();
    }

    private String describe() {
        if (page == null) return "Reading page. No page is loaded.";
        StringBuilder text = new StringBuilder("Reading page ");
        text.append(page.index + 1);
        if (page.fixed) text.append(" of ").append(page.pageCount);
        text.append(". Long press or use Select to choose text.");
        if (selection != null && selection.text != null && selection.text.length() > 0) {
            text.append(" Selection: ").append(clip(selection.text, 120));
        }
        return text.toString();
    }

    @Override public AccessibilityNodeProvider getAccessibilityNodeProvider() {
        return provider;
    }

    @Override public void onInitializeAccessibilityNodeInfo(AccessibilityNodeInfo info) {
        super.onInitializeAccessibilityNodeInfo(info);
        info.setClassName(ReaderView.class.getName());
        info.setContentDescription(describe());
        info.setScrollable(false);
    }

    private AccessibilityNodeInfo hostNode() {
        AccessibilityNodeInfo info = AccessibilityNodeInfo.obtain(this);
        onInitializeAccessibilityNodeInfo(info);
        info.setSource(this);
        for (int i = 1; i <= lineText.length; i++) info.addChild(this, i);
        return info;
    }

    private Rect screenBounds(RectF bounds) {
        Rect rect = new Rect();
        if (bounds == null) return rect;
        int[] location = new int[2];
        getLocationOnScreen(location);
        rect.set(Math.round(location[0] + toViewX(bounds.left)),
                Math.round(location[1] + toViewY(bounds.top)),
                Math.round(location[0] + toViewX(bounds.right)),
                Math.round(location[1] + toViewY(bounds.bottom)));
        return rect;
    }

    private float toViewX(float contentX) {
        return contentX * page.renderScale * fit + offsetX;
    }

    private float toViewY(float contentY) {
        return contentY * page.renderScale * fit + offsetY;
    }

    private float toContentX(float viewX) {
        return ((viewX - offsetX) / fit) / page.renderScale;
    }

    private float toContentY(float viewY) {
        return ((viewY - offsetY) / fit) / page.renderScale;
    }

    private void computeFit() {
        if (page == null || page.bitmap == null) {
            fit = 1f;
            offsetX = 0f;
            offsetY = 0f;
            return;
        }
        float width = Math.max(1, getWidth() - 16f);
        float height = Math.max(1, getHeight() - 16f);
        fit = Math.min(width / page.bitmap.getWidth(), height / page.bitmap.getHeight());
        if (!(fit > 0f)) fit = 1f;
        offsetX = (getWidth() - page.bitmap.getWidth() * fit) / 2f;
        offsetY = (getHeight() - page.bitmap.getHeight() * fit) / 2f;
    }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        canvas.drawColor(Color.rgb(247, 247, 242));
        if (page == null || page.bitmap == null) {
            canvas.drawText("No page loaded", 40f, 80f, emptyPaint);
            return;
        }
        computeFit();
        RectF destination = new RectF(offsetX, offsetY,
                offsetX + page.bitmap.getWidth() * fit,
                offsetY + page.bitmap.getHeight() * fit);
        canvas.drawBitmap(page.bitmap, null, destination, bitmapPaint);
        if (selection != null) {
            for (RectF rect : selection.rects) {
                canvas.drawRect(toViewX(rect.left), toViewY(rect.top), toViewX(rect.right), toViewY(rect.bottom), selectionPaint);
            }
            if (!selection.rects.isEmpty()) {
                RectF first = selection.rects.get(0);
                RectF last = selection.rects.get(selection.rects.size() - 1);
                canvas.drawCircle(toViewX(first.left), toViewY(first.top), 9f, handlePaint);
                canvas.drawCircle(toViewX(last.right), toViewY(last.bottom), 9f, handlePaint);
            }
        }
    }

    @Override protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
        super.onSizeChanged(width, height, oldWidth, oldHeight);
        computeFit();
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (page == null) return false;
        computeFit();
        float x = event.getX();
        float y = event.getY();
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                down = true;
                moved = false;
                longPress = false;
                downX = x;
                downY = y;
                if (selectMode) {
                    int hit = hit(x, y);
                    if (hit >= 0) {
                        anchor = hit;
                        focus = hit;
                        updateSelection(true);
                    }
                } else {
                    handler.postDelayed(longPressRunnable, LONG_PRESS_MS);
                }
                return true;
            case MotionEvent.ACTION_MOVE:
                if (Math.abs(x - downX) > 8f || Math.abs(y - downY) > 8f) {
                    moved = true;
                    handler.removeCallbacks(longPressRunnable);
                }
                if (selectMode && anchor >= 0) {
                    int hit = hit(x, y);
                    if (hit >= 0 && hit != focus) {
                        focus = hit;
                        updateSelection(true);
                    }
                }
                return true;
            case MotionEvent.ACTION_UP:
                handler.removeCallbacks(longPressRunnable);
                if (selectMode) {
                    if (anchor >= 0 && selection == null) updateSelection(true);
                    down = false;
                    return true;
                }
                if (!moved && !longPress) {
                    int zone = x < getWidth() * 0.3f ? -1 : x > getWidth() * 0.7f ? 1 : 0;
                    if (zone != 0 && listener != null) listener.onTapZone(zone);
                }
                down = false;
                performClick();
                return true;
            case MotionEvent.ACTION_CANCEL:
                handler.removeCallbacks(longPressRunnable);
                down = false;
                return true;
            default:
                return super.onTouchEvent(event);
        }
    }

    @Override public boolean performClick() {
        super.performClick();
        return true;
    }

    private int hit(float viewX, float viewY) {
        if (page == null) return -1;
        float x = toContentX(viewX);
        float y = toContentY(viewY);
        if (!page.fixed) {
            int count = page.glyphCount();
            int nearest = -1;
            float distance = 40f;
            for (int i = 0; i < count; i++) {
                float top = page.glyphBaseline[i] - page.glyphSize[i];
                float bottom = page.glyphBaseline[i] + page.glyphSize[i] * 0.3f;
                float left = page.glyphX[i] - 2f;
                float right = page.glyphX[i] + page.glyphAdvance[i] + 2f;
                if (x >= left && x <= right && y >= top && y <= bottom) return i;
                float dx = Math.max(left - x, Math.max(0f, x - right));
                float dy = Math.max(top - y, Math.max(0f, y - bottom));
                float candidate = (float) Math.hypot(dx, dy);
                if (candidate < distance) {
                    distance = candidate;
                    nearest = i;
                }
            }
            return nearest;
        }
        int count = page.regionCount();
        int nearest = -1;
        float distance = 30f;
        for (int i = 0; i < count; i++) {
            RectF box = quadBox(page.quads[i]);
            if (box.contains(x, y)) return i;
            float dx = Math.max(box.left - x, Math.max(0f, x - box.right));
            float dy = Math.max(box.top - y, Math.max(0f, y - box.bottom));
            float candidate = (float) Math.hypot(dx, dy);
            if (candidate < distance) {
                distance = candidate;
                nearest = i;
            }
        }
        return nearest;
    }

    private void updateSelection(boolean notify) {
        if (page == null || anchor < 0 || focus < 0) return;
        int low = Math.min(anchor, focus);
        int high = Math.max(anchor, focus);
        long start;
        long end;
        List<RectF> rects = new ArrayList<>();
        if (!page.fixed) {
            start = Long.MAX_VALUE;
            end = 0;
            for (int i = low; i <= high && i < page.glyphCount(); i++) {
                start = Math.min(start, page.starts[i]);
                end = Math.max(end, page.ends[i]);
                rects.add(glyphBox(i));
            }
        } else {
            start = Long.MAX_VALUE;
            end = 0;
            for (int i = low; i <= high && i < page.regionCount(); i++) {
                start = Math.min(start, page.starts[i]);
                end = Math.max(end, page.ends[i]);
                rects.add(quadBox(page.quads[i]));
            }
        }
        if (start == Long.MAX_VALUE) {
            selection = null;
            invalidate();
            return;
        }
        String text = ReflowSession.slice(page.text, start, end);
        selection = new Selection(page.index, start, end, text, rects);
        setContentDescription(describe());
        invalidate();
        if (notify && listener != null) listener.onSelectionChanged(selection);
    }

    private RectF glyphBox(int index) {
        float top = page.glyphBaseline[index] - page.glyphSize[index];
        float bottom = page.glyphBaseline[index] + page.glyphSize[index] * 0.2f;
        return new RectF(page.glyphX[index] - 1f, top,
                page.glyphX[index] + page.glyphAdvance[index] + 1f, bottom);
    }

    private static RectF quadBox(float[] quad) {
        float left = Math.min(Math.min(quad[0], quad[2]), Math.min(quad[4], quad[6]));
        float top = Math.min(Math.min(quad[1], quad[3]), Math.min(quad[5], quad[7]));
        float right = Math.max(Math.max(quad[0], quad[2]), Math.max(quad[4], quad[6]));
        float bottom = Math.max(Math.max(quad[1], quad[3]), Math.max(quad[5], quad[7]));
        return new RectF(left, top, right, bottom);
    }

    static String clip(String value, int limit) {
        if (value == null) return "";
        return value.length() <= limit ? value : value.substring(0, limit) + "...";
    }
}
