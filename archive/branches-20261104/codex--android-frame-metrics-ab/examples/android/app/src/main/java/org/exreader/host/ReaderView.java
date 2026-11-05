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
    private long acceptedToken, renderRevision, drawnToken=-1, drawnRevision=-1, settledToken=-1, settledRevision=-1;
    private long drawnNanos, settledNanos;
    private int drawnWidth, drawnHeight;
    private float drawnFit, drawnX, drawnY;
    private String pointHash;
    private org.json.JSONObject debugBitmapIdentity;

    private static String bitmapHash(java.security.MessageDigest digest) {
        StringBuilder hash=new StringBuilder();
        for(byte value:digest.digest()) hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
        return hash.toString();
    }

    /** Diagnostic identity of the accepted Bitmap before Canvas/GPU sampling. */
    private static org.json.JSONObject bitmapIdentity(Bitmap bitmap) {
        try {
            java.security.MessageDigest logical=java.security.MessageDigest.getInstance("SHA-256");
            int width=bitmap.getWidth(),height=bitmap.getHeight();
            int[] pixels=new int[width];
            byte[] row=new byte[width*4];
            for(int y=0;y<height;y++) {
                bitmap.getPixels(pixels,0,width,0,y,width,1);
                for(int x=0;x<width;x++) {
                    int value=pixels[x],at=x*4;
                    row[at]=(byte)(value>>>24);row[at+1]=(byte)(value>>>16);
                    row[at+2]=(byte)(value>>>8);row[at+3]=(byte)value;
                }
                logical.update(row);
            }
            java.nio.ByteBuffer raw=java.nio.ByteBuffer.allocate(bitmap.getByteCount());
            bitmap.copyPixelsToBuffer(raw);
            java.security.MessageDigest storage=java.security.MessageDigest.getInstance("SHA-256");
            storage.update(raw.array(),0,raw.position());
            return new org.json.JSONObject().put("logical_argb_sha256",bitmapHash(logical))
                .put("raw_sha256",bitmapHash(storage)).put("width",width).put("height",height)
                .put("row_bytes",bitmap.getRowBytes()).put("byte_count",bitmap.getByteCount())
                .put("config",String.valueOf(bitmap.getConfig())).put("premultiplied",bitmap.isPremultiplied())
                .put("has_alpha",bitmap.hasAlpha()).put("color_space",String.valueOf(bitmap.getColorSpace()));
        } catch(java.security.NoSuchAlgorithmException | org.json.JSONException error) {
            throw new IllegalStateException(error);
        }
    }

    private void renderChanged() {
        if (!BuildConfig.DEBUG) return;
        renderRevision++; drawnToken=settledToken=-1; drawnRevision=settledRevision=-1;
    }

    private void observedDraw() {
        if (!BuildConfig.DEBUG || page==null || (drawnToken==acceptedToken && drawnRevision==renderRevision)) return;
        final PageSnapshot captured=page;
        final long token=acceptedToken, revision=renderRevision;
        final int width=getWidth(), height=getHeight();
        drawnToken=token; drawnRevision=revision; drawnWidth=width; drawnHeight=height;
        drawnFit=fit; drawnX=offsetX; drawnY=offsetY; drawnNanos=System.nanoTime();
        // This is an after-draw/settled observation, not a compositor presentation fence.
        postOnAnimation(()->postOnAnimation(()->{
            if(page!=captured || acceptedToken!=token || renderRevision!=revision ||
                    drawnToken!=token || drawnRevision!=revision || getWidth()!=width || getHeight()!=height) return;
            settledToken=token; settledRevision=revision; settledNanos=System.nanoTime();
            sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
        }));
    }

    private String frameObservation() {
        try {
            org.json.JSONObject state=new org.json.JSONObject()
                .put("pid",android.os.Process.myPid()).put("view",System.identityHashCode(this))
                .put("accepted_token",acceptedToken).put("revision",renderRevision)
                .put("drawn_token",drawnToken).put("drawn_revision",drawnRevision)
                .put("settled_token",settledToken).put("settled_revision",settledRevision)
                .put("drawn_ns",drawnNanos).put("settled_ns",settledNanos)
                .put("viewport_width",getWidth()).put("viewport_height",getHeight())
                .put("drawn_width",drawnWidth).put("drawn_height",drawnHeight)
                .put("fit",drawnFit).put("offset_x",drawnX).put("offset_y",drawnY)
                .put("selection_mode",selectMode).put("selection_start",selection==null?-1:selection.start)
                .put("selection_end",selection==null?-1:selection.end);
            if(BuildConfig.DEBUG && debugBitmapIdentity!=null) state.put("bitmap_identity",debugBitmapIdentity);
            if(page!=null) state.put("book",page.bookId).put("index",page.index).put("part",page.part)
                .put("path",page.path==null?org.json.JSONObject.NULL:page.path).put("start",page.start).put("end",page.end)
                .put("anchor_sha256",pointHash==null?org.json.JSONObject.NULL:pointHash)
                .put("anchor_kind",page.bounded?"bounded_point":page.fixed?"fixed_page":"source_offset")
                .put("font",page.fixed?org.json.JSONObject.NULL:page.layoutFont).put("zoom",page.layoutZoom)
                .put("render_scale",page.renderScale).put("bitmap_width",page.bitmap.getWidth()).put("bitmap_height",page.bitmap.getHeight())
                .put("glyph_font_first",page.glyphSize==null || page.glyphSize.length==0?org.json.JSONObject.NULL:page.glyphSize[0]);
            return state.toString();
        } catch(org.json.JSONException error) { throw new IllegalStateException(error); }
    }

    private final Runnable longPressRunnable = new Runnable() {
        @Override public void run() {
            if (!isEnabled() || !down || moved || selectMode || page == null) return;
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
        // Keep UI bitmap resampling deterministic in one viewport-sized software layer.
        setLayerType(FrameMetricsTrace.layerType(getContext()), null);
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
        handler.removeCallbacks(longPressRunnable);
        down = false;
        page = snapshot;
        if(BuildConfig.DEBUG) {
            debugBitmapIdentity=snapshot==null ? null : bitmapIdentity(snapshot.bitmap);
            acceptedToken++; renderChanged(); pointHash=null;
            if(snapshot!=null && snapshot.boundedLocation!=null) {
                try {
                    byte[] bytes=new org.json.JSONArray(java.util.Arrays.asList(snapshot.boundedLocation)).toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    byte[] digest=java.security.MessageDigest.getInstance("SHA-256").digest(bytes);
                    StringBuilder hash=new StringBuilder(); for(byte value:digest) hash.append(String.format(java.util.Locale.ROOT,"%02x",value&255));
                    pointHash=hash.toString();
                } catch(java.security.NoSuchAlgorithmException error) { throw new IllegalStateException(error); }
            }
        }
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
        if(snapshot!=null && snapshot.highlightStart>=0) {
            for(int i=0;i<snapshot.glyphCount();i++) if(snapshot.ends[i]>snapshot.highlightStart && snapshot.starts[i]<snapshot.highlightEnd) {
                if(anchor<0) anchor=i; focus=i;
            }
            if(anchor>=0) updateSelection(false);
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
        renderChanged();
        if (!enabled) {
            selection = null;
            anchor = -1;
            focus = -1;
            invalidate();
            if (listener != null) listener.onSelectionCleared();
        }
        setContentDescription(describe());
        if(BuildConfig.DEBUG) invalidate();
        if (listener != null) listener.onSelectModeChanged(enabled);
    }

    public Selection getSelection() {
        return selection;
    }

    public void clearSelection() {
        renderChanged();
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
        if(BuildConfig.DEBUG) info.getExtras().putString("exreader.frame",frameObservation());
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
        if (bounds == null || page == null) return rect;
        computeFit();
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
        observedDraw();
    }

    @Override protected void onSizeChanged(int width, int height, int oldWidth, int oldHeight) {
        super.onSizeChanged(width, height, oldWidth, oldHeight);
        computeFit();
        renderChanged();
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (!isEnabled() || page == null) return false;
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
            renderChanged();
            invalidate();
            return;
        }
        String text = ReflowSession.slice(page.text, start - page.textBase, end - page.textBase);
        selection = new Selection(page.index, start, end, text, rects);
        renderChanged();
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
