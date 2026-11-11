/* SPDX-License-Identifier: MIT */
/* Checks the production host, including HWND dispatch and CF_UNICODETEXT. */
#define WinMain reader_WinMain
#define EXR_READER_TEST_DRIVERS 1
#include "../reader.c"
#undef WinMain
#include <assert.h>

static const char *fixture =
  "<html lang='en'><body><p>紅樓夢中文。 Alpha bravo, can't co-operate café. 👩‍💻</p>"
  "<p>Second paragraph has enough words to wrap across several physical rows and pages for keyboard and selection checks.</p>"
  "<p>Third paragraph.</p><p>Fourth paragraph.</p><p>Fifth paragraph.</p>"
  "<p>hyphenation hyphenation hyphenation hyphenation hyphenation hyphenation</p></body></html>";
static char fixture_path[4096];
static exr_status fixture_load(void *context, size_t part, exr_document **out, exr_error *error) {
  (void)context; (void)part;
  if (fixture_path[0]) return exr_document_open(fixture_path, out, error);
  exr_document *plain = NULL;
  exr_status status = exr_document_open_memory(EXR_HTML, fixture, strlen(fixture), &plain, error);
  if (status != EXR_OK) return status;
  size_t count = 0; const exr_block *blocks = exr_document_blocks(plain, &count);
  const char *text = exr_document_text(plain, NULL);
  exr_node_input *nodes = calloc(2+count*2, sizeof(*nodes)); assert(nodes);
  exr_attribute lang = {"lang", "en"};
  nodes[0] = (exr_node_input){EXR_NODE_DOCUMENT, SIZE_MAX, NULL, NULL, NULL, 0};
  nodes[1] = (exr_node_input){EXR_NODE_CHAPTER, 0, NULL, NULL, &lang, 1};
  for (size_t i = 0; i < count; i++) {
    size_t size = blocks[i].end-blocks[i].start;
    char *copy = malloc(size+1); assert(copy); memcpy(copy, text+blocks[i].start, size); copy[size] = 0;
    nodes[2+i*2] = (exr_node_input){EXR_NODE_PARAGRAPH, 1, "p", NULL, NULL, 0};
    nodes[3+i*2] = (exr_node_input){EXR_NODE_TEXT, 2+i*2, NULL, copy, NULL, 0};
  }
  exr_chapter_input chapter = {"fixture", "fixture.html", 1, 1};
  exr_document_input input = {"Selection", nodes, 2+count*2, &chapter, 1, NULL, 0};
  status = exr_document_create(&input, out, error);
  for (size_t i = 0; i < count; i++) free((void *)nodes[3+i*2].text);
  free(nodes); exr_document_free(plain); return status;
}
static void ok(exr_status status, exr_error *error) {
  if (status != EXR_OK) { fprintf(stderr, "%d: %s\n", status, error ? error->message : "SDK call failed"); exit(1); }
}
static void expect_text(const char *expected) {
  char *copy = NULL; size_t size = shell_selection_bytes(&copy);
  assert(copy && size == strlen(expected) && !memcmp(copy, expected, size)); free(copy);
}
static void bounds(const char *text) {
  exr_document *document = NULL; ok(fixture_load(NULL, 0, &document, NULL), NULL);
  const char *source = exr_document_text(document, NULL), *found = strstr(source, text); assert(found);
  size_t at = (size_t)(found-source);
  exr_text_position point = {0, at};
  assert(select_set(point, point, EXR_RANGE_WORD, 1)); expect_text(text);
  printf("WORD %zu %zu %s\n", select_range.start.offset, select_range.end.offset, text);
  exr_document_free(document);
}
static void test_boundaries(void) {
  const char *words[] = {"紅", "樓", "夢", "中", "文", "Alpha", "bravo", "can", "co", "operate", "café", "👩‍💻", ",", "'", "-"};
  for (size_t i = 0; i < sizeof(words)/sizeof(*words); i++) bounds(words[i]);
  exr_document *document = NULL; ok(fixture_load(NULL, 0, &document, NULL), NULL);
  size_t count = 0; const exr_block *blocks = exr_document_blocks(document, &count); assert(count >= 5);
  for (size_t i = 0; i < 5; i++) {
    exr_text_position point = {0, blocks[i].start};
    assert(select_set(point, point, EXR_RANGE_PARAGRAPH, 1));
    assert(select_range.start.offset == blocks[i].start && select_range.end.offset == blocks[i].end);
    printf("PARAGRAPH %zu %zu\n", select_range.start.offset, select_range.end.offset);
  }
  exr_text_range_match match = {0};
  ok(exr_range_from_anchor(g.session.publication, &select_anchor, NULL, &match, NULL), NULL);
  assert(match.state == EXR_ANCHOR_FOUND && match.range.start.offset == select_range.start.offset && match.range.end.offset == select_range.end.offset);
  exr_document_free(document);
}
static void test_copy(void) {
  exr_document *document = NULL; size_t size = 0;
  ok(fixture_load(NULL, 0, &document, NULL), NULL);
  const char *source = exr_document_text(document, &size);
  assert(select_set((exr_text_position){0, 0}, (exr_text_position){1, size}, -1, 1));
  char *copy = NULL; size_t copied = shell_selection_bytes(&copy);
  assert(copied == size*2 && !memcmp(copy, source, size) && !memcmp(copy+size, source, size));
  assert(clipboard_set(copy, copied));
  assert(OpenClipboard(g.window)); HANDLE memory = GetClipboardData(CF_UNICODETEXT); assert(memory);
  wchar_t *wide = GlobalLock(memory); assert(wide); char *utf8 = host_utf8(wide);
  assert(strlen(utf8) == copied && !memcmp(copy, utf8, copied));
  free(utf8); GlobalUnlock(memory); CloseClipboard(); free(copy);
  for (int i = 0; i < 3; i++) {
    g.frame.part = (size_t)(i%2); select_all_part();
    assert(select_range.start.part == g.frame.part && select_range.end.part == g.frame.part);
    assert(select_range.start.offset == 0 && select_range.end.offset == size);
    expect_text(source);
  }
  puts("COPY cross-part exact; clipboard roundtrip; Ctrl+A 3/3");
  exr_document_free(document);
}
static void load_frame(size_t page) {
  frame_clear(&g.frame); ok(render_reflow(&g.session, page, &g.frame, NULL, NULL), NULL);
  g.session.page = page; compute_view();
}
static void prepare_layout(int vertical) {
  g.session.config = exr_layout_config_defaults();
  g.session.config.page = (exr_layout_options){260, 160, 0, 14, 1.5f, 0};
  g.session.config.user_css = vertical ? "p{writing-mode:vertical-rl;margin:0;padding:0}" : "p{margin:0;padding:0;hyphens:auto}";
  g.session.shell_geometry = (shell_geometry){1, 260, 160, vertical, 96, 14, {14, 1.5f, 0, 0, 0, 0, 0, 0}};
  exr_pager_free(g.session.pager); g.session.pager = NULL;
  exr_document_free(g.session.document); g.session.document = NULL; g.session.bounded = 0;
  ok(fixture_load(NULL, 0, &g.session.document, NULL), NULL);
  ok(exr_pager_create(g.session.document, g.font, &g.session.config, &g.session.pager, NULL), NULL);
  load_frame(0); g.frame.part = g.session.part = 0;
}
static void test_keyboard(void) {
  prepare_layout(0); shell_active = 1;
  select_origin = select_focus = (exr_text_position){0, 0}; select_valid = 0;
  select_drive_key(VK_RIGHT, 1, 0); assert(select_range.start.offset == 0 && select_range.end.offset == 3);
  select_drive_key(VK_RIGHT, 1, 0); assert(select_range.end.offset == 6);
  select_drive_key(VK_LEFT, 1, 0); assert(select_range.end.offset == 3);
  select_drive_key(VK_DOWN, 1, 0); assert(select_focus.offset > 3);
  select_drive_key(VK_UP, 1, 0); assert(select_focus.offset <= 6);
  select_drive_key(VK_ESCAPE, 0, 0); assert(!select_valid && !g.selection.active && !select_drag);
  for (int i = 0; i < 3; i++) {
    select_drive_key('A', 0, 1); assert(select_range.start.offset == 0 && select_range.end.offset > g.frame.range_end);
    select_drive_key('C', 0, 1); assert(clipboard_contains("Alpha"));
    select_drive_key(VK_ESCAPE, 0, 0); assert(!g.selection.active);
  }
  HMENU menu = select_context_menu(); assert(GetMenuItemCount(menu) == 13);
  assert(GetMenuState(menu, 100, MF_BYCOMMAND) != (UINT)-1);
  assert(!(GetMenuState(menu, 101, MF_BYCOMMAND)&MF_GRAYED));
  assert(GetMenuState(menu, 102, MF_BYCOMMAND)&MF_GRAYED);
  assert(GetMenuState(menu, 103, MF_BYCOMMAND)&MF_GRAYED);
  assert(GetMenuState(menu, 8, MF_BYCOMMAND)&MF_GRAYED);
  assert(GetMenuState(menu, 1, MF_BYCOMMAND)&MF_GRAYED);
  assert(!(GetMenuState(menu, 2, MF_BYCOMMAND)&MF_GRAYED));
  assert(GetMenuState(menu, 3, MF_BYCOMMAND)&MF_GRAYED); DestroyMenu(menu);
  select_drive_key('A', 0, 1); menu = select_context_menu();
  assert(!(GetMenuState(menu, 8, MF_BYCOMMAND)&MF_GRAYED));
  assert(!(GetMenuState(menu, 1, MF_BYCOMMAND)&MF_GRAYED)); DestroyMenu(menu);
  puts("SHIFT inline 3/3; row 2/2; Ctrl+A/C/Esc 3/3");
}
static void test_raster(void) {
  for (int vertical = 0; vertical < 2; vertical++) {
    shell_active = 0; prepare_layout(vertical);
    size_t at = g.frame.glyphs[0].cluster_start;
    select_origin = select_focus = (exr_text_position){0, at};
    select_focus.offset += 15;
    assert(select_set(select_origin, select_focus, EXR_RANGE_CHAR, 1));
    HRGN region = select_region(); RECT box; assert(GetRgnBox(region, &box) != NULLREGION);
    printf("region mode=%d requested=%d box=%ld,%ld,%ld,%ld lines=%zu flags=%u\n", g.frame.writing_mode, vertical,
      box.left, box.top, box.right, box.bottom, g.frame.shell_line_count, g.frame.glyphs[0].flags);
    if (vertical) assert(box.bottom-box.top > box.right-box.left);
    else assert(box.right-box.left > box.bottom-box.top);
    DeleteObject(region);
    size_t bytes = g.frame.bitmap.stride*g.frame.bitmap.height;
    unsigned char *saved = malloc(bytes); assert(saved); memcpy(saved, g.frame.bitmap.pixels, bytes);
    shell_active = 1;
    for (int theme = 0; theme < 2; theme++) {
      shell_theme_mode = theme; shell_colors = theme ? &shell_theme_dark : &shell_theme_light;
      shell_color_display(&g.frame);
      HDC screen = GetDC(g.page), dc = CreateCompatibleDC(screen);
      HBITMAP image = CreateCompatibleBitmap(screen, 800, 800); ReleaseDC(g.page, screen);
      HGDIOBJ old = SelectObject(dc, image); shell_selection_paint(dc);
      assert(!memcmp(saved, g.frame.bitmap.pixels, bytes));
      SelectObject(dc, old); DeleteObject(image); DeleteDC(dc);
    }
    free(saved);
    puts(vertical ? "RASTER vertical + light/dark unchanged" : "RASTER horizontal + light/dark unchanged");
  }
}
static void test_generated(void) {
  prepare_layout(0);
  exr_pager_free(g.session.pager); g.session.pager = NULL;
  g.session.config.page.width = 55; g.session.config.page.margin = 10;
  g.session.config.user_css = "html,body,p{margin:0;padding:0;font-size:14px;line-height:20px}";
  ok(exr_pager_create(g.session.document, g.font, &g.session.config, &g.session.pager, NULL), NULL);
  exr_hyphenator *hyphenator = NULL;
  exr_hyphen_pattern_input input = {sizeof(input), "en", "aa1aaaa aaaa1aa f1if1if1if1i", 0, 1, 1};
  input.size = strlen(input.patterns);
  ok(exr_hyphenator_create_patterns(&input, 1, 0, NULL, &hyphenator, NULL), NULL);
  ok(exr_pager_set_hyphenator(g.session.pager, hyphenator, NULL), NULL);
  exr_hyphenator_free(hyphenator); load_frame(0);
  size_t generated = 0;
  for (size_t i = 0; i < g.frame.glyph_count; i++) generated += !!(g.frame.glyphs[i].flags & EXR_GLYPH_GENERATED);
  printf("hyphen glyphs=%zu lines=%zu\n", g.frame.glyph_count, g.frame.shell_line_count);
  assert(generated > 0); select_all_part();
  char *copy = NULL; size_t bytes = shell_selection_bytes(&copy);
  assert(bytes > 0 && !strstr(copy, "\xe2\x80\x90"));
  size_t source_size = 0; const char *source = exr_document_text(g.session.document, &source_size);
  assert(bytes == source_size && !memcmp(copy, source, bytes)); free(copy);
  printf("HYPHENS generated=%zu U+2010=0 exact=1\n", generated);
  fixture_path[0] = 0; fixture = "<html><body><p>12</p></body></html>";
  shell_active = 0; prepare_layout(1);
  exr_pager_free(g.session.pager); g.session.pager = NULL;
  g.session.config.user_css = "p{writing-mode:vertical-rl;text-combine-upright:all}";
  ok(exr_pager_create(g.session.document, g.font, &g.session.config, &g.session.pager, NULL), NULL);
  load_frame(0); size_t combined = 0;
  for (size_t i = 0; i < g.frame.glyph_count; i++) combined += !!(g.frame.glyphs[i].flags & EXR_GLYPH_COMBINED);
  assert(combined == 2); select_all_part(); expect_text("12");
  puts("COMBINE glyphs=2 copied-bytes=2 extra-bytes=0");
}
#include "check_shell_annotations.inc"
#include "check_shell_shelf.inc"
#include "check_shell_style.inc"
#include "check_shell_shelfmeta.inc"
#include "check_shell_dictionary.inc"
int main(int argc, char **argv) {
  setvbuf(stdout, NULL, _IONBF, 0);
  assert(argc == 3); SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
  host_offscreen = 1; InitializeCriticalSection(&g.library_lock);
  g.window = CreateWindowW(L"STATIC", L"Selection test", WS_POPUP, -32000, -32000, 800, 800, NULL, NULL, NULL, NULL);
  WNDCLASSW type = {0}; type.lpfnWndProc = page_procedure; type.lpszClassName = L"SelectionTestPage"; RegisterClassW(&type);
  g.page = CreateWindowW(type.lpszClassName, L"", WS_CHILD, 0, 0, 800, 800, g.window, NULL, NULL, NULL); assert(g.page);
  ok(exr_font_open(argv[2], &g.font, NULL), NULL);
  exr_part parts[] = {{"one", "one.html", "One", 1}, {"two", "two.html", "Two", 1}};
  exr_publication_input input = {"Selection", parts, 2, fixture_load, NULL, NULL, NULL, 0};
  ok(exr_publication_create(&input, &g.session.publication, NULL), NULL);
  g.session.active = g.session.bounded = g.frame.valid = 1;
  g.frame.book_id = g.session.book_id = 1;
  if (!strcmp(argv[1], "shelf")) test_shelf();
  else if (!strcmp(argv[1], "annotations")) test_annotations();
  else if (!strcmp(argv[1], "style")) test_style();
  else if (!strcmp(argv[1], "shelfmeta")) test_shelfmeta();
  else if (!strcmp(argv[1], "dictionary-storage")) test_dictionary_storage();
  else if (!strcmp(argv[1], "boundaries")) test_boundaries();
  else if (!strcmp(argv[1], "copy")) test_copy();
  else if (!strcmp(argv[1], "keyboard")) test_keyboard();
  else if (!strcmp(argv[1], "raster")) test_raster();
  else if (!strcmp(argv[1], "generated")) {
    /* argv[2] is a font file, so form the sibling fixture path explicitly. */
    snprintf(fixture_path, sizeof(fixture_path), "%s", argv[2]);
    char *slash = strrchr(fixture_path, '/'); if (!slash) slash = strrchr(fixture_path, '\\'); assert(slash); *slash = 0;
    strncat(fixture_path, "/../hyphen-long.epub", sizeof(fixture_path)-strlen(fixture_path)-1);
    test_generated();
  }
  else return 2;
  shell_selection_reset(); frame_clear(&g.frame); session_clear(&g.session); exr_font_free(g.font);
  DestroyWindow(g.window); DeleteCriticalSection(&g.library_lock); puts("PASS"); return 0;
}
