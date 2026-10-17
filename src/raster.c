/* SPDX-License-Identifier: GPL-3.0-only */
#include "layout_internal.h"
#include "pixels_internal.h"
#include FT_SYNTHESIS_H
#include FT_TRUETYPE_TABLES_H
#include FT_OUTLINE_H
static void rectangle(exr_bitmap *b, float x, float y, float w, float h, uint32_t color) {
  int left = (int)fmaxf(0, floorf(x)), top = (int)fmaxf(0, floorf(y));
  int right = (int)fminf((float)b->width, ceilf(x + w)),
      bottom = (int)fminf((float)b->height, ceilf(y + h));
  int xx, yy;
  if (!(color & 255) || w <= 0 || h <= 0)
    return;
  for (yy = top; yy < bottom; yy++)
    for (xx = left; xx < right; xx++)
      exr_pixel(b, xx, yy, color, 255);
}
static void decoration(exr_bitmap *out,const exr_glyph *g,const exr_glyph *next,FT_Face face,const exr_line *line) {
  float thickness=fmaxf(1,fminf(g->size/6,(float)FT_MulFix(face->underline_thickness,face->size->metrics.y_scale)/64));
  if(g->flags&EXR_GLYPH_VERTICAL) {
    float top=fmaxf(floorf(g->baseline),ceilf(g->clip_left)),bottom=g->baseline+g->advance;
    float center=line ? line->x+line->width/2 : g->x;
    float edge=line ? line->x+line->width-thickness : g->x+g->size/2-thickness;
    if(next && !(next->flags&EXR_GLYPH_HIDDEN) && (next->flags&EXR_DECORATIONS)==(g->flags&EXR_DECORATIONS) &&
       next->color==g->color) bottom=fmaxf(bottom,next->baseline);
    bottom=fminf(ceilf(bottom),ceilf(g->clip_right));
    if(g->flags&EXR_GLYPH_UNDERLINE) rectangle(out,edge,top,thickness,bottom-top,g->color);
    if(g->flags&EXR_GLYPH_STRIKE) rectangle(out,center,top,thickness,bottom-top,g->color);
    return;
  }
  float left=fmaxf(floorf(g->x),ceilf(g->clip_left)),right=g->x+g->advance;
  if(next && !(next->flags&EXR_GLYPH_HIDDEN) && (next->flags&EXR_DECORATIONS)==(g->flags&EXR_DECORATIONS) &&
      next->color==g->color && fabsf(next->baseline-g->baseline)<0.01f) right=fmaxf(right,next->x);
  right=fminf(ceilf(right),ceilf(g->clip_right));
  if(g->flags&EXR_GLYPH_UNDERLINE) {
    float position=(float)FT_MulFix(face->underline_position,face->size->metrics.y_scale)/64;
    rectangle(out,left,g->baseline-position,right-left,thickness,g->color);
  }
  if(g->flags&EXR_GLYPH_STRIKE) {
    const TT_OS2 *os2=FT_Get_Sfnt_Table(face,ft_sfnt_os2);
    float position=g->size*0.3f,strike_thickness=thickness;
    if(os2) {
      position=(float)FT_MulFix(os2->yStrikeoutPosition,face->size->metrics.y_scale)/64;
      strike_thickness=fmaxf(1,fminf(g->size/6,(float)FT_MulFix(os2->yStrikeoutSize,face->size->metrics.y_scale)/64));
    }
    rectangle(out,left,g->baseline-position,right-left,strike_thickness,g->color);
  }
}
static exr_status picture(exr_bitmap *out, const exr_box *box, const exr_bitmap *src,
                             const exr_control *control, exr_error *error) {
  int left = (int)fmaxf(0, ceilf(box->x)), top = (int)fmaxf(0, ceilf(box->y));
  int right = (int)fminf((float)out->width, ceilf(box->x + box->width));
  int bottom = (int)fminf((float)out->height, ceilf(box->y + box->height));
  int x, y;
  if (box->width <= 0 || box->height <= 0)
    return EXR_OK;
  for (y = top; y < bottom; y++) {
    if (!(y & 63) && exr_control_cancel(control, error) != EXR_OK) return EXR_CANCELLED;
    for (x = left; x < right; x++) {
      float sx =
          fmaxf(0, fminf((float)src->width - 1,
                         ((float)x + 0.5f - box->x) / box->width * (float)src->width - 0.5f));
      float sy =
          fmaxf(0, fminf((float)src->height - 1,
                         ((float)y + 0.5f - box->y) / box->height * (float)src->height - 0.5f));
      uint32_t x0 = (uint32_t)sx, y0 = (uint32_t)sy;
      uint32_t x1 = x0 + 1 < src->width ? x0 + 1 : x0, y1 = y0 + 1 < src->height ? y0 + 1 : y0;
      float fx = sx - (float)x0, fy = sy - (float)y0;
      float weights[4] = {(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy};
      const unsigned char *samples[4] = {src->pixels + (size_t)y0 * src->stride + x0 * 4,
                                         src->pixels + (size_t)y0 * src->stride + x1 * 4,
                                         src->pixels + (size_t)y1 * src->stride + x0 * 4,
                                         src->pixels + (size_t)y1 * src->stride + x1 * 4};
      float alpha = 0, colors[3] = {0};
      unsigned k, channel;
      uint32_t color = 0;
      for (k = 0; k < 4; k++) {
        float a = weights[k] * (float)samples[k][3];
        alpha += a;
        for (channel = 0; channel < 3; channel++)
          colors[channel] += a * (float)samples[k][channel];
      }
      if (alpha <= 0)
        continue;
      for (channel = 0; channel < 3; channel++)
        color = (color << 8) | (uint32_t)lroundf(colors[channel] / alpha);
      color = (color << 8) | (uint32_t)lroundf(alpha);
      exr_pixel(out, x, y, color, 255);
    }
  }
  return EXR_OK;
}
static exr_status draw_box(exr_bitmap *out,const exr_layout *l,const exr_box *b,
                             const exr_control *control,exr_error *e) {
  size_t j; float bw=fminf(b->border_width,fminf(b->width,b->height)/2);
  rectangle(out,b->x,b->y,b->width,b->height,b->background);
  if(b->kind==EXR_BOX_IMAGE && !b->flags) for(j=0;j<l->image_count;j++) if(l->images[j].resource==b->resource) {
    exr_status status=picture(out,b,&l->images[j].bitmap,control,e); if(status!=EXR_OK) return status;
    break;
  }
  if(bw>0) {
    rectangle(out,b->x,b->y,b->width,bw,b->border_color);
    rectangle(out,b->x,b->y+b->height-bw,b->width,bw,b->border_color);
    rectangle(out,b->x,b->y,bw,b->height,b->border_color);
    rectangle(out,b->x+b->width-bw,b->y,bw,b->height,b->border_color);
  }
  return EXR_OK;
}
static exr_status draw_glyph(exr_bitmap *out,exr_font *font,const exr_glyph *g,const exr_glyph *next,const exr_line *line) {
  exr_face *selected; FT_Face face; FT_GlyphSlot slot; unsigned by,bx; int left,top;
  if((g->flags&EXR_GLYPH_HIDDEN) || g->size<1.0f/64) return EXR_OK;
  if(g->font_index>=font->count) return EXR_FONT;
  selected=&font->faces[g->font_index]; face=selected->face;
  if(exr_font_size(selected,g->size) || FT_Load_Glyph(face,g->glyph,FT_LOAD_DEFAULT)) return EXR_FONT;
  if(g->flags&1) FT_GlyphSlot_Embolden(face->glyph);
  if(g->flags&2) FT_GlyphSlot_Oblique(face->glyph);
  if(face->glyph->format==FT_GLYPH_FORMAT_OUTLINE) {
    FT_BBox bounds; double width,height;
    FT_Outline_Get_CBox(&face->glyph->outline,&bounds);
    width=ceil((double)bounds.xMax/64)-floor((double)bounds.xMin/64);
    height=ceil((double)bounds.yMax/64)-floor((double)bounds.yMin/64);
    if(width>8192 || height>8192 || width*height>16*1024*1024) return EXR_LIMIT;
  }
  if(FT_Render_Glyph(face->glyph,FT_RENDER_MODE_NORMAL)) return EXR_FONT;
  slot=face->glyph;
  left=(int)lroundf(g->x+g->offset_x)+slot->bitmap_left;
  top=(int)lroundf(g->baseline-g->offset_y)-slot->bitmap_top;
  if(g->flags&EXR_GLYPH_SIDEWAYS) {
    left=(int)lroundf(g->x+g->offset_y)+slot->bitmap_top-1;
    top=(int)lroundf(g->baseline+g->offset_x)+slot->bitmap_left;
  }
  for(by=0;by<slot->bitmap.rows;by++) for(bx=0;bx<slot->bitmap.width;bx++) {
    int sideways=!!(g->flags&EXR_GLYPH_SIDEWAYS);
    int x=sideways ? left-(int)by : left+(int)bx,y=sideways ? top+(int)bx : top+(int)by;
    float inline_position=(float)((g->flags&EXR_GLYPH_VERTICAL) ? y : x);
    const unsigned char *row; unsigned a;
    if(x<0 || y<0 || (uint32_t)x>=out->width || (uint32_t)y>=out->height ||
       inline_position<g->clip_left || inline_position>=g->clip_right) continue;
    row=slot->bitmap.buffer+(ptrdiff_t)by*slot->bitmap.pitch;
    if(slot->bitmap.pixel_mode==FT_PIXEL_MODE_GRAY) a=row[bx];
    else if(slot->bitmap.pixel_mode==FT_PIXEL_MODE_MONO) a=(row[bx/8]&(0x80>>(bx%8))) ? 255 : 0;
    else continue;
    exr_pixel(out,x,y,g->color,a);
  }
  if(g->flags&EXR_DECORATIONS) decoration(out,g,next,face,line);
  return EXR_OK;
}
static const exr_line *glyph_line(const exr_layout *l,size_t glyph) {
  size_t lo=0,hi=l->line_count;
  while(lo<hi) {
    size_t mid=lo+(hi-lo)/2; const exr_line *line=&l->lines[mid];
    if(glyph<line->glyph_start) hi=mid;
    else if(glyph-line->glyph_start>=line->glyph_count) lo=mid+1;
    else return line;
  }
  return NULL;
}
static exr_status render(const exr_layout *l, exr_font *f, size_t page, unsigned channels,
                         const exr_control *control, exr_bitmap *out, exr_error *e) {
  size_t i, j, total; exr_status status=EXR_OK;
  uint32_t width, height;
  const exr_page *p;
  if (l && l->font && (!f || f == l->font || f == l->font->fallback)) f = l->font;
  if (!l || (!f && (!l->positioned || l->glyph_count)) || !out || page >= l->page_count || (channels != 1 && channels != 4))
    return exr_fail(e, EXR_ARGUMENT, "Invalid render arguments");
  memset(out, 0, sizeof(*out));
  total=l->positioned ? l->positioned[page].paint_count : l->pages[page].box_count+l->pages[page].line_count;
  if (exr_control_poll(control, EXR_STAGE_RENDER, 0,total, e) != EXR_OK)
    return EXR_CANCELLED;
  width = (uint32_t)ceilf(l->options.width);
  height = (uint32_t)ceilf(l->options.height);
  if ((size_t)width * height * channels > 64 * 1024 * 1024)
    return exr_fail(e, EXR_LIMIT, "Page bitmap exceeds 64 MiB");
  out->pixels = malloc((size_t)width * height * channels);
  if (!out->pixels)
    return EXR_MEMORY;
  out->width = width;
  out->height = height;
  out->stride = width * channels;
  out->channels = channels;
  memset(out->pixels, 255, (size_t)out->stride * height);
  p = &l->pages[page];
  if(l->positioned) {
    const exr_positioned_page *positioned=&l->positioned[page];
    for(i=0;i<positioned->paint_count;i++) {
      const exr_paint *command=&l->paints[positioned->paint_start+i];
      if(!(i&31) && exr_control_poll(control,EXR_STAGE_RENDER,i,total,e)!=EXR_OK) goto cancelled;
      if(command->kind==EXR_PAINT_GLYPH) {
        status=draw_glyph(out,f,&l->glyphs[command->index],NULL,glyph_line(l,command->index)); if(status!=EXR_OK) goto font_error;
      } else if(draw_box(out,l,&l->boxes[command->index],control,e)!=EXR_OK) goto cancelled;
    }
  } else {
    for(i=p->box_start;i<p->box_start+p->box_count;i++) {
      if(exr_control_poll(control,EXR_STAGE_RENDER,i-p->box_start,total,e)!=EXR_OK) goto cancelled;
      if(draw_box(out,l,&l->boxes[i],control,e)!=EXR_OK) goto cancelled;
    }
    for(i=p->line_start;i<p->line_start+p->line_count;i++) {
      size_t end=l->lines[i].glyph_start+l->lines[i].glyph_count;
      for(j=l->lines[i].glyph_start;j<end;j++) {
        if(j==l->lines[i].glyph_start && exr_control_poll(control,EXR_STAGE_RENDER,p->box_count+i-p->line_start,total,e)!=EXR_OK) goto cancelled;
        if(!(j&31) && exr_control_cancel(control,e)!=EXR_OK) goto cancelled;
        status=draw_glyph(out,f,&l->glyphs[j],j+1<end ? &l->glyphs[j+1] : NULL,&l->lines[i]); if(status!=EXR_OK) goto font_error;
      }
    }
  }
  if (exr_control_poll(control, EXR_STAGE_RENDER,total,total,e) != EXR_OK) goto cancelled;
  return exr_fail(e, EXR_OK, "");
cancelled:
  exr_bitmap_free(out);
  return exr_fail(e, EXR_CANCELLED, "Operation cancelled");
font_error:
  exr_bitmap_free(out);
  return exr_fail(e,status,status==EXR_LIMIT ? "Glyph bitmap exceeds 8192 pixels or 16 million pixels" : "Glyph rasterization failed");
}
exr_status exr_render_page(const exr_layout *l, exr_font *f, size_t page, exr_bitmap *out,
                           exr_error *e) {
  return render(l, f, page, 1, NULL, out, e);
}
exr_status exr_render_page_color(const exr_layout *l, exr_font *f, size_t page, exr_bitmap *out,
                                 exr_error *e) {
  return render(l, f, page, 4, NULL, out, e);
}
exr_status exr_render_page_ex(const exr_layout *l, exr_font *f, size_t page, unsigned channels,
                               const exr_control *control, exr_bitmap *out, exr_error *e) {
  return render(l, f, page, channels, control, out, e);
}
