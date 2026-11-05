# EXReader Android Display 0.1.0

Optional native Java Android AAR, API 26+, Java 17. No SDK/core dependency,
parser, network, global settings, preferences, permission, service, wake lock,
reflection, or JNI. Independent of existing hosts and default builds.

Build/install in Actions: Gradle 8.9 / AGP 8.6.1 / compileSdk 35;
`:display:assembleRelease` produces `display-release.aar`. Install that file
plus this README under a prefix. A fresh consumer uses
`implementation files('/installed/prefix/exreader-android-display-0.1.0.aar')`.
The probe build does exactly this from a separate copied directory.

```java
// Activity main thread; acquire only the Activity's own Window.
ReaderDisplay display = new ReaderDisplay();
ReaderDisplay.Status attached = display.attach(getWindow());
long token = display.generation();
display.configure(token, ReaderDisplay.FOLLOW_SYSTEM, true);
// Call only when host considers reading active and window has focus.
display.activate(token);
// In onPause/cancel or when host stops reading:
display.deactivate(token);
// Rotation: old owner must release before binding the new Window.
display.detach(token);
// A new attach produces a different token; old callbacks get STALE_GENERATION.
display.close();
```

Every mutator returns a `Status` with no effect on guard/input failure. Check
statuses; neither `activate` nor `configure` waits for a future visible window.
Wrong thread, synchronous Window callback reentry, repeat attach, conflict,
stale token, closed owner, null/finishing/destroyed/non-Activity Window and
nonfinite/out-of-range brightness are rejected. `-1` remains system-following;
otherwise the hard range is finite `[0,1]`. There are no string/Unicode inputs.
`generation()` is the only cross-thread read; zero means never attached.

A lease is exclusive per Window, including while inactive. Distinct Activity
windows are independent. All state is main-looper confined, bounded to one
Window and constant-sized listener/state records per owner. Close/detach must
be called; registered lifecycle destruction also detaches. No callback supplied
by this API, background work, queued operation or asynchronous cancellation.
Host Window callbacks must not throw exceptions: arbitrary framework/host
callback exceptions are not converted into successful Status values.

Only focused, attached, visible windows can activate. Automatic pause, stop,
focus-loss and decor-detach listeners restore and disarm; automatic destruction
releases the lease. Regaining focus requires **new explicit activation**.
Host code must also call deactivate when its reader becomes hidden inside a
still-focused Activity. Hosts should call it before `super.onPause()` if their
own pause hook requires already-restored properties.

A single `setAttributes` commits both fields, preserving unrelated properties.
Restore compares each field against the last value this owner actually wrote;
only still-owned values are undone. Untouched/preexisting keep-screen-on is
never cleared. An external change observed on release is retained. On a later
explicit reconfiguration, an external value becomes the new restoration base.
Android provides no authorship/version stamp: an external write of the exact
same value (or a change away and back between observations) is indistinguishable.
Cooperating hosts must deactivate before same-value writes; this limitation is
not presented as global or cross-process ownership.

`restore` equals `deactivate`: cancel own edits but keep lease and desired
settings. `detach` revokes the token and permits attach to a replacement Window;
`close` releases and permanently rejects subsequent calls, including another
close. Process death destroys Window state; the library persists nothing.

API34 emulator tests establish Window property behavior only. Physical backlight,
screen-off policy, battery savings, OEM behavior and accessibility remain
UNAVAILABLE without device measurement. Formal host integration is not included.

Android API references:
- https://developer.android.com/reference/android/view/WindowManager.LayoutParams#screenBrightness
- https://developer.android.com/reference/android/view/WindowManager.LayoutParams#FLAG_KEEP_SCREEN_ON
- https://developer.android.com/reference/android/app/Application.ActivityLifecycleCallbacks
