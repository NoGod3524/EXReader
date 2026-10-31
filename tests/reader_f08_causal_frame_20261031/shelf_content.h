/* SPDX-License-Identifier: MIT
 * Read-only native content snapshot shared by the observer and isolated control.
 */
#ifndef F08_SHELF_CONTENT_H
#define F08_SHELF_CONTENT_H
#include <gtk/gtk.h>
#include <math.h>
#include <stdint.h>
typedef struct {
 gint64 at,top_id;
 int index,x,y,width,height;
 double scroll;
 gboolean available,list_drawable,row_drawable,clip_intersects;
} F08ShelfContent;
static F08ShelfContent f08_shelf_content(GtkWidget *list,cairo_t *cr){
 F08ShelfContent out={0};out.top_id=-1;out.index=-1;out.scroll=-1;
 if(!GTK_IS_LIST_BOX(list) || !cr)goto done;
 GtkWidget *scroll=gtk_widget_get_ancestor(list,GTK_TYPE_SCROLLED_WINDOW);
 if(!scroll)goto done;
 GtkAdjustment *adjustment=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(scroll));
 out.scroll=gtk_adjustment_get_value(adjustment);
 if(!isfinite(out.scroll) || out.scroll<0 || out.scroll>G_MAXINT){out.scroll=-1;goto done;}
 /* This is the product's shelf_top_row algorithm, observed through public GTK. */
 GtkListBoxRow *row=gtk_list_box_get_row_at_y(GTK_LIST_BOX(list),(int)out.scroll);
 if(!row)goto done;
 const int64_t *id=g_object_get_data(G_OBJECT(row),"book-id");
 if(!id || *id<=0)goto done;
 GtkAllocation allocation;gtk_widget_get_allocation(GTK_WIDGET(row),&allocation);
 if(!gtk_widget_translate_coordinates(GTK_WIDGET(row),list,0,0,&out.x,&out.y))goto done;
 out.top_id=*id;out.index=gtk_list_box_row_get_index(row);
 out.width=allocation.width;out.height=allocation.height;
 out.list_drawable=gtk_widget_is_drawable(list);out.row_drawable=gtk_widget_is_drawable(GTK_WIDGET(row));
 out.available=out.index>=0 && out.width>0 && out.height>0;
 cairo_rectangle_list_t *clip=cairo_copy_clip_rectangle_list(cr);
 if(clip->status==CAIRO_STATUS_SUCCESS && clip->num_rectangles<=128){
  for(int i=0;i<clip->num_rectangles;i++){
   const cairo_rectangle_t *r=clip->rectangles+i;
   if(r->width>0 && r->height>0 && r->x<out.x+out.width && r->x+r->width>out.x &&
      r->y<out.y+out.height && r->y+r->height>out.y){out.clip_intersects=TRUE;break;}
  }
 }
 cairo_rectangle_list_destroy(clip);
done:
 out.at=g_get_monotonic_time();return out;
}
#endif
