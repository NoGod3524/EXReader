/* Small GTK workload used only to test the frame-clock probe. */
#include <gtk/gtk.h>
static gboolean tick(gpointer data) {
    static int count;
    gtk_widget_queue_draw(GTK_WIDGET(data));
    if (++count == 20) { gtk_main_quit(); return G_SOURCE_REMOVE; }
    return G_SOURCE_CONTINUE;
}
int main(int argc, char **argv) {
    gtk_init(&argc, &argv);
    GtkWidget *window = gtk_window_new(GTK_WINDOW_TOPLEVEL);
    gtk_window_set_default_size(GTK_WINDOW(window), 320, 240);
    gtk_widget_show_all(window);
    g_timeout_add(40, tick, window);
    gtk_main();
    return 0;
}
