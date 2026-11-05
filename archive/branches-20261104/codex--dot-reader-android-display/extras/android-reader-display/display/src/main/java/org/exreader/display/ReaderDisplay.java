// SPDX-License-Identifier: MIT
package org.exreader.display;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.ContextWrapper;
import android.os.Bundle;
import android.os.Looper;
import android.view.View;
import android.view.ViewTreeObserver;
import android.view.Window;
import android.view.WindowManager;
import java.util.IdentityHashMap;

/**
 * Main-thread, exclusive, ephemeral Activity-Window lease. No permissions,
 * settings, services, persistence or wake locks. See the installed README.
 * All mutations return a Status; generation() is a read-only volatile snapshot.
 */
public final class ReaderDisplay {
    public static final String VERSION = "0.1.0";
    public static final float FOLLOW_SYSTEM = -1.0f;
    public enum Status {
        OK, WRONG_THREAD, REENTRANT, CLOSED, ALREADY_ATTACHED, NOT_ATTACHED,
        INVALID_WINDOW, CONFLICT, STALE_GENERATION, INVALID_BRIGHTNESS, NOT_VISIBLE
    }
    private static final int KEEP = WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON;
    // Accessed only on the main looper. Explicit close/destroy releases entries.
    private static final IdentityHashMap<Window, ReaderDisplay> LEASES = new IdentityHashMap<>();
    private Window window;
    private Activity activity;
    private View decor;
    private ViewTreeObserver observer;
    private ViewTreeObserver.OnWindowFocusChangeListener focus;
    private View.OnAttachStateChangeListener attachment;
    private Application.ActivityLifecycleCallbacks lifecycle;
    private volatile long generation;
    private boolean closed, busy, active, ownsBrightness, ownsKeep;
    private float desiredBrightness = FOLLOW_SYSTEM, beforeBrightness, lastBrightness;
    private boolean desiredKeep, beforeKeep, lastKeep;

    public long generation() { return generation; }

    private Status entry() {
        if (Looper.myLooper() != Looper.getMainLooper()) return Status.WRONG_THREAD;
        if (busy) return Status.REENTRANT;
        if (closed) return Status.CLOSED;
        return Status.OK;
    }
    private Status attached(long token) {
        Status status = entry();
        if (status != Status.OK) return status;
        if (token != generation) return Status.STALE_GENERATION;
        if (window == null) return Status.NOT_ATTACHED;
        return Status.OK;
    }
    private static Activity findActivity(Context context) {
        for (int depth = 0; depth < 32; depth++) {
            if (context instanceof Activity) return (Activity) context;
            if (!(context instanceof ContextWrapper)) return null;
            Context next = ((ContextWrapper) context).getBaseContext();
            if (next == context) return null;
            context = next;
        }
        return null;
    }
    public Status attach(Window target) {
        Status status = entry();
        if (status != Status.OK) return status;
        if (window != null) return Status.ALREADY_ATTACHED;
        Activity owner = target == null ? null : findActivity(target.getContext());
        if (owner == null || owner.isDestroyed() || owner.isFinishing()
                || owner.getWindow() != target) return Status.INVALID_WINDOW;
        if (LEASES.containsKey(target)) return Status.CONFLICT;
        busy = true;
        try {
            window = target; activity = owner; decor = target.getDecorView();
            generation++;
            final long token = generation;
            // Capture actual pre-lease attributes; each subsequent acquisition
            // also samples current attributes, never a stale global preference.
            beforeBrightness = target.getAttributes().screenBrightness;
            beforeKeep = (target.getAttributes().flags & KEEP) != 0;
            LEASES.put(target, this);
            focus = hasFocus -> { if (!hasFocus) deactivate(token); };
            observer = decor.getViewTreeObserver();
            observer.addOnWindowFocusChangeListener(focus);
            attachment = new View.OnAttachStateChangeListener() {
                public void onViewAttachedToWindow(View view) { }
                public void onViewDetachedFromWindow(View view) { deactivate(token); }
            };
            decor.addOnAttachStateChangeListener(attachment);
            lifecycle = new Application.ActivityLifecycleCallbacks() {
                public void onActivityPaused(Activity a) { if (a == owner) deactivate(token); }
                public void onActivityStopped(Activity a) { if (a == owner) deactivate(token); }
                public void onActivityDestroyed(Activity a) { if (a == owner) detach(token); }
                public void onActivityCreated(Activity a, Bundle state) { }
                public void onActivityStarted(Activity a) { }
                public void onActivityResumed(Activity a) { }
                public void onActivitySaveInstanceState(Activity a, Bundle state) { }
            };
            owner.getApplication().registerActivityLifecycleCallbacks(lifecycle);
            return Status.OK;
        } finally { busy = false; }
    }
    private boolean visible() {
        return !activity.isDestroyed() && !activity.isFinishing()
                && decor.isAttachedToWindow() && decor.getWindowVisibility() == View.VISIBLE
                && decor.getVisibility() == View.VISIBLE && decor.hasWindowFocus();
    }
    /** Stages settings while inactive. Both inputs are validated before any write. */
    public Status configure(long token, float brightness, boolean keepScreenOn) {
        Status status = attached(token);
        if (status != Status.OK) return status;
        if (!Float.isFinite(brightness) || !(brightness == FOLLOW_SYSTEM || brightness >= 0f && brightness <= 1f))
            return Status.INVALID_BRIGHTNESS;
        busy = true;
        try {
            desiredBrightness = brightness; desiredKeep = keepScreenOn;
            if (active && visible()) apply();
            else if (active) { active = false; releaseEdits(); }
            return Status.OK;
        } finally { busy = false; }
    }
    /** Requires a currently focused visible window; never arms a future focus event. */
    public Status activate(long token) {
        Status status = attached(token);
        if (status != Status.OK) return status;
        if (!visible()) return Status.NOT_VISIBLE;
        busy = true;
        try { active = true; apply(); return Status.OK; }
        finally { busy = false; }
    }
    /** Cancel/restore: relinquish own edits, retain lease/configuration, disarm activation. */
    public Status deactivate(long token) {
        Status status = attached(token);
        if (status != Status.OK) return status;
        busy = true;
        try { active = false; releaseEdits(); return Status.OK; }
        finally { busy = false; }
    }
    public Status restore(long token) { return deactivate(token); }

    private static boolean equal(float a, float b) {
        return Float.floatToIntBits(a) == Float.floatToIntBits(b);
    }
    private WindowManager.LayoutParams copy() {
        WindowManager.LayoutParams params = new WindowManager.LayoutParams();
        params.copyFrom(window.getAttributes());
        return params;
    }
    private void apply() {
        WindowManager.LayoutParams params = copy();
        boolean keep = (params.flags & KEEP) != 0;
        // An observed external write ends our ownership of that field. A new
        // explicit configure/activate can acquire it again, from that new value.
        if (ownsBrightness && !equal(params.screenBrightness, lastBrightness)) ownsBrightness = false;
        if (ownsKeep && keep != lastKeep) ownsKeep = false;
        boolean changed = false;
        if (!equal(params.screenBrightness, desiredBrightness)) {
            if (!ownsBrightness) beforeBrightness = params.screenBrightness;
            ownsBrightness = true; lastBrightness = desiredBrightness;
            params.screenBrightness = desiredBrightness; changed = true;
        }
        if (keep != desiredKeep) {
            if (!ownsKeep) beforeKeep = keep;
            ownsKeep = true; lastKeep = desiredKeep;
            params.flags = desiredKeep ? params.flags | KEEP : params.flags & ~KEEP;
            changed = true;
        }
        // Single commit preserves unrelated attributes and makes validation
        // failures atomic. Android callbacks must not throw (documented contract).
        if (changed) window.setAttributes(params);
    }
    private void releaseEdits() {
        WindowManager.LayoutParams params = copy();
        boolean changed = false;
        if (ownsBrightness && equal(params.screenBrightness, lastBrightness)) {
            params.screenBrightness = beforeBrightness; changed = true;
        }
        if (ownsKeep && ((params.flags & KEEP) != 0) == lastKeep) {
            params.flags = beforeKeep ? params.flags | KEEP : params.flags & ~KEEP; changed = true;
        }
        ownsBrightness = false; ownsKeep = false;
        if (changed) window.setAttributes(params);
    }
    public Status detach(long token) {
        Status status = attached(token);
        if (status != Status.OK) return status;
        busy = true;
        try { detachInternal(); return Status.OK; }
        finally { busy = false; }
    }
    private void detachInternal() {
        active = false; releaseEdits();
        if (observer.isAlive()) observer.removeOnWindowFocusChangeListener(focus);
        else if (decor.getViewTreeObserver().isAlive())
            decor.getViewTreeObserver().removeOnWindowFocusChangeListener(focus);
        decor.removeOnAttachStateChangeListener(attachment);
        activity.getApplication().unregisterActivityLifecycleCallbacks(lifecycle);
        LEASES.remove(window);
        window = null; activity = null; decor = null; observer = null;
        focus = null; attachment = null; lifecycle = null; generation++;
    }
    /** Not idempotent: a second close returns CLOSED. No owner survives Activity destruction. */
    public Status close() {
        Status status = entry();
        if (status != Status.OK) return status;
        busy = true;
        try {
            if (window != null) detachInternal();
            closed = true; return Status.OK;
        } finally { busy = false; }
    }
}
