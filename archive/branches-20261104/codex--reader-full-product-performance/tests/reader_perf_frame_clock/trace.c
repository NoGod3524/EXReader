/* Performance-only interception: observe GDK after-paint clock signals. */
#define _GNU_SOURCE
#include <gtk/gtk.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static void on_after_paint(GdkFrameClock *clock, gpointer ignored) {
    (void)ignored;
    const char *directory = getenv("EXR_FRAME_TRACE_DIR");
    if (!directory || !*directory) return;
    char path[4096];
    if (snprintf(path, sizeof(path), "%s/%ld.tsv", directory, (long)getpid()) >= (int)sizeof(path)) return;
    struct timespec stamp;
    if (clock_gettime(CLOCK_MONOTONIC, &stamp) != 0) return;
    FILE *out = fopen(path, "a");
    if (!out) return;
    fprintf(out, "%p\t%lld\t%lld\n", (void *)clock,
            (long long)gdk_frame_clock_get_frame_time(clock),
            (long long)stamp.tv_sec * 1000000LL + stamp.tv_nsec / 1000);
    fclose(out);
}

void gdk_frame_clock_request_phase(GdkFrameClock *clock, GdkFrameClockPhase phase) {
    static void (*next)(GdkFrameClock *, GdkFrameClockPhase);
    if (!next) next = dlsym(RTLD_NEXT, "gdk_frame_clock_request_phase");
    if (!next) abort();
    if (getenv("EXR_FRAME_TRACE_DIR") && !g_object_get_data(G_OBJECT(clock), "exr-perf-frame-clock")) {
        g_object_set_data(G_OBJECT(clock), "exr-perf-frame-clock", GINT_TO_POINTER(1));
        g_signal_connect(clock, "after-paint", G_CALLBACK(on_after_paint), NULL);
    }
    next(clock, phase);
}
