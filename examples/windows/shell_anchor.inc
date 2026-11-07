/* SPDX-License-Identifier: MIT */
/* A resolved content point is a viewport head, not just a containing page.
   Keep the SDK's shaping/rasterization; join visible line bands from its owned
   frames. The same operation serves document, bounded EPUB and TXT reflow. */
static exr_status shell_align_anchor(host_session *session, size_t offset, host_frame *frame,
                                    const exr_control *control, exr_error *error) {
  host_frame view = {0}, next = {0}, *source = frame;
  exr_status status = EXR_OK;
  size_t page = frame->page, pixels = (size_t)frame->bitmap.width * frame->bitmap.height;
  int vertical = frame->writing_mode != EXR_WRITING_HORIZONTAL_TB;
  int reverse = frame->writing_mode == EXR_WRITING_VERTICAL_RL;
  float used = 0, extent = vertical ? frame->bitmap.width : frame->bitmap.height;
  int full = 0;
  if (!session->shell_geometry.enabled || !frame->shell_line_count ||
      offset == frame->shell_lines[0].start) return EXR_OK;
  if (offset < frame->range_start || offset >= frame->range_end) return EXR_ARGUMENT;
  view.bitmap = frame->bitmap; view.bitmap.pixels = malloc(view.bitmap.stride * view.bitmap.height);
  view.dib = malloc(pixels * sizeof(*view.dib));
  view.utf8 = malloc(HOST_PAGE_TEXT_LIMIT + 1);
  if (!view.bitmap.pixels || !view.dib || !view.utf8) { status = EXR_MEMORY; goto done; }
  memset(view.bitmap.pixels, 255, view.bitmap.stride * view.bitmap.height);
  view.range_start = view.range_end = offset;
  for (size_t guard = 0; guard < 8 && !full; guard++) {
    size_t count = source->shell_line_count, first = 0;
    exr_line *lines = realloc(view.shell_lines, (view.shell_line_count + count) * sizeof(*lines));
    if (!lines) { status = EXR_MEMORY; goto done; } view.shell_lines = lines;
    if (view.glyph_count + source->glyph_count > HOST_PAGE_GLYPH_LIMIT) { status = EXR_LIMIT; goto done; }
    exr_glyph *glyphs = realloc(view.glyphs, (view.glyph_count + source->glyph_count) * sizeof(*glyphs));
    if (!glyphs) { status = EXR_MEMORY; goto done; } view.glyphs = glyphs;
    while (first < count && source->shell_lines[first].end <= offset) first++;
    size_t end = source->range_end;
    for (size_t i = first; i < count; i++) {
      exr_line line = source->shell_lines[i];
      float span = vertical ? line.width : line.height;
      /* Retain paragraph gaps within a natural page. */
      if (i + 1 < count) span = vertical ? fabsf(source->shell_lines[i+1].x-line.x) : source->shell_lines[i+1].y-line.y;
      if (used + (vertical ? line.width : line.height) > extent + .01f) { end = line.start; full = 1; break; }
      float dx = vertical ? (reverse ? extent-used-line.width : used)-line.x : 0;
      float dy = vertical ? 0 : used-line.y;
      size_t glyph_start = view.glyph_count, old_start = line.glyph_start;
      float trim = 0;
      if (!view.shell_line_count && offset > line.start) {
        size_t g = old_start;
        while (g < old_start+line.glyph_count && source->glyphs[g].start < offset) g++;
        if (g == old_start+line.glyph_count || source->glyphs[g].start != offset) { status = EXR_FORMAT; goto done; }
        trim = vertical ? source->glyphs[g].baseline-source->glyphs[old_start].baseline : source->glyphs[g].x-source->glyphs[old_start].x;
        old_start = g; line.start = offset;
      }
      for (size_t g = old_start; g < source->shell_lines[i].glyph_start+source->shell_lines[i].glyph_count; g++) {
        exr_glyph glyph = source->glyphs[g];
        glyph.x += dx-(vertical ? 0 : trim); glyph.baseline += dy-(vertical ? trim : 0);
        view.glyphs[view.glyph_count++] = glyph;
      }
      /* Copy the same band as the coordinates above, including book decoration. */
      int x0 = vertical ? (int)floorf(line.x) : 0;
      int x1 = vertical ? (int)ceilf(line.x+line.width) : (int)view.bitmap.width;
      int y0 = vertical ? 0 : (int)floorf(line.y);
      int y1 = vertical ? (int)view.bitmap.height : (int)ceilf(line.y+fminf(span, extent-used));
      for (int y = y0; y < y1 && y < (int)source->bitmap.height; y++) for (int x = x0; x < x1 && x < (int)source->bitmap.width; x++) {
        int tx = x+(int)lroundf(dx)-(vertical ? 0 : (int)lroundf(trim));
        int ty = y+(int)lroundf(dy)-(vertical ? (int)lroundf(trim) : 0);
        if (x < 0 || y < 0 || tx < 0 || ty < 0 || tx >= (int)view.bitmap.width || ty >= (int)view.bitmap.height) continue;
        if (trim && (vertical ? y < line.y+trim : x < line.x+trim)) continue;
        memcpy(view.bitmap.pixels+ty*view.bitmap.stride+tx*4, source->bitmap.pixels+y*source->bitmap.stride+x*4, 4);
      }
      line.x += dx; line.y += dy; line.glyph_start = glyph_start; line.glyph_count = view.glyph_count-glyph_start;
      if (vertical) line.height -= trim; else line.width -= trim;
      view.shell_lines[view.shell_line_count++] = line;
      used += span;
    }
    size_t start = source == frame ? offset : source->range_start;
    if (start < view.range_end || end < start || end-source->range_start > source->text_bytes || end-offset > HOST_PAGE_TEXT_LIMIT) { status = EXR_LIMIT; goto done; }
    if (start > view.range_end) {
      size_t gap = start-view.range_end;
      if (session->document) {
        size_t size = 0; const char *text = exr_document_text(session->document, &size);
        if (start > size) { status = EXR_FORMAT; goto done; }
        memcpy(view.utf8+view.range_end-offset, text+view.range_end, gap);
      } else if (session->bounded) {
        host_text_sink sink = {view.utf8+view.range_end-offset, 0, gap};
        status = exr_pager_read_text(session->pager, view.range_end, start, page_text_sink, &sink, control, error);
        if (status != EXR_OK) goto done;
      } else {
        /* TXT projection separates paragraphs with exactly one LF. */
        if (gap != 1) { status = EXR_FORMAT; goto done; }
        view.utf8[view.range_end-offset] = '\n';
      }
    }
    memcpy(view.utf8+start-offset, source->utf8+start-source->range_start, end-start);
    view.range_end = end;
    if (full || used >= extent) break;
    frame_clear(&next);
    if (session->txt) {
      const exr_layout *layout = NULL;
      status = exr_pager_get(session->pager, ++page, &layout, error);
      if (status == EXR_OK) status = txt_frame(session, &session->txt_source, layout, page, &next, error);
    } else
    status = render_reflow(session, ++page, &next, control, error);
    if (pager_eof(status, error)) { status = EXR_OK; memset(error, 0, sizeof(*error)); break; }
    if (status != EXR_OK) goto done;
    source = &next;
  }
  view.text_bytes = view.range_end-offset; view.utf8[view.text_bytes] = 0;
  view.text = host_wide(view.utf8, view.text_bytes);
  if (!view.text || !view.shell_line_count) { status = EXR_FORMAT; goto done; }
  for (size_t i = 0; i < pixels; i++) {
    const unsigned char *p = view.bitmap.pixels+(i/view.bitmap.width)*view.bitmap.stride+(i%view.bitmap.width)*4;
    view.dib[i] = (p[0]<<16)|(p[1]<<8)|p[2];
  }
  if (frame->hit_layout) {
    exr_positioned_page positioned = {0}; exr_positioned_input input = {0};
    exr_layout_config hit = exr_layout_config_defaults();
    positioned.width = view.bitmap.width; positioned.height = view.bitmap.height;
    positioned.content = (exr_page){offset, view.range_end, 0, view.shell_line_count, 0, 0};
    input.struct_size = sizeof(input); input.pages = &positioned; input.page_count = 1;
    input.glyphs = view.glyphs; input.glyph_count = view.glyph_count;
    input.lines = view.shell_lines; input.line_count = view.shell_line_count;
    hit.page.width = positioned.width; hit.page.height = positioned.height; hit.page.margin = 0;
    status = exr_layout_create_positioned(session->document, exr_layout_font(frame->hit_layout), &input, &hit, &view.hit_layout, error);
    if (status != EXR_OK) goto done;
  }
  if (session->bounded) {
    status = exr_pager_anchor_create(session->pager, offset, offset, control, &view.point, error);
    if (status != EXR_OK) goto done;
  }
  view.valid = 1; view.book_id = frame->book_id; view.part = frame->part; view.page = frame->page;
  view.bounded = frame->bounded; view.hold_progress = frame->hold_progress; view.render_scale = 1;
  view.generation = frame->generation; view.shell_geometry = frame->shell_geometry;
  view.writing_mode = frame->writing_mode; view.shell_anchored = 1;
  frame_move(frame, &view);
done:
  frame_clear(&view); frame_clear(&next);
  return status;
}
