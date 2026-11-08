/* SPDX-License-Identifier: MIT */
/* Startup only: the immutable index and the body font outlive every book. */
static exr_status host_open_body_font(const wchar_t *file, const wchar_t *config, exr_error *error) {
  static const char *const fallback[] = {"Noto Serif CJK SC", "Source Han Serif SC", "SimSun"};
  exr_font_manager_options options = {0};
  exr_font_location location = {0};
  exr_font_manager_summary summary = {0};
  exr_font_pick_result pick = {0};
  exr_font_face_info face = {0};
  wchar_t directory[HOST_PATH], cache[HOST_PATH];
  char *input, *cache_path;
  const char *family = "serif";
  size_t *faces = NULL, count = 0;
  exr_status status;
  module_directory(directory, HOST_PATH);
  path_join(cache, HOST_PATH, g.data_dir, L"font-index.cache");
  input = host_utf8(config[0] ? config : file[0] ? file : directory);
  cache_path = host_utf8(cache);
  if (!input || !cache_path) { free(input); free(cache_path); return EXR_MEMORY; }
  options.struct_size = sizeof(options);
  location.path = input;
  location.kind = file[0] ? EXR_FONT_LOCATION_FILE : EXR_FONT_LOCATION_DIRECTORY;
  options.locations = &location; options.location_count = 1;
  options.cache_path = cache_path;
  if (!file[0]) {
    options.flags = EXR_FONT_MANAGER_PLATFORM_DIRECTORIES;
    options.fallback_families = fallback; options.fallback_count = sizeof(fallback)/sizeof(*fallback);
    options.serif_families = "Noto Serif SC, Noto Serif CJK SC, Source Han Serif SC, SimSun";
    options.sans_serif_families = "Noto Sans CJK SC, Noto Sans SC, Microsoft YaHei, SimHei, Arial";
  }
  status = config[0] ? exr_font_manager_open(input, &g.font_manager, error) :
                      exr_font_manager_create(&options, &g.font_manager, error);
  free(input); free(cache_path);
  if (status != EXR_OK) return status;
  summary.struct_size = sizeof(summary);
  exr_font_manager_summary_get(g.font_manager, &summary, NULL);
  if (file[0] && !config[0]) {
    face.struct_size = sizeof(face);
    status = exr_font_manager_face(g.font_manager, 0, &face, error);
    if (status != EXR_OK) return status;
    family = face.family;
  }
  status = exr_font_manager_create_font(g.font_manager, family, EXR_FONT_STYLE_REGULAR,
                                        &g.font, &faces, &count, error);
  if (status != EXR_OK) return status;
  /* Keep #70's regular body weight. Reuse manager-loaded bytes and order;
     no discovery or file loading is performed by the host. */
  exr_font_axis *axes = NULL; size_t axis_count = 0;
  if ((!file[0] || config[0]) && exr_font_axes(g.font, 0, &axes, &axis_count, NULL) == EXR_OK)
    for (size_t a = 0; a < axis_count; a++)
      if (axes[a].tag == 0x77676874u && axes[a].value != 400 && axes[a].minimum <= 400 && axes[a].maximum >= 400) {
        exr_font_input sources[EXR_FONT_CHAIN_MAX];
        exr_font_coordinate weight = {0, 0x77676874u, 400};
        exr_font *regular = NULL;
        for (size_t i = 0; i < count; i++) exr_font_source(g.font, i, &sources[i], NULL);
        status = exr_font_create_variable(sources, count, &weight, 1, &regular, error);
        if (status == EXR_OK) { exr_font_free(g.font); g.font = regular; }
        break;
      }
  exr_free(axes);
  if (status != EXR_OK) { exr_free(faces); return status; }
  pick.struct_size = sizeof(pick);
  status = exr_font_manager_pick(g.font_manager, family, EXR_FONT_STYLE_REGULAR, 0x4e2d, &pick, error);
  if (status == EXR_OK && pick.face == SIZE_MAX)
    status = exr_font_manager_pick(g.font_manager, family, EXR_FONT_STYLE_REGULAR, 'A', &pick, error);
  /* Use the actual loaded mapping if a file disappeared after indexing. */
  size_t selected = SIZE_MAX;
  for (size_t i = 0; i < count; i++)
    if (exr_font_has_glyph(g.font, i, 0x4e2d)) { selected = faces[i]; break; }
  if (selected == SIZE_MAX && count) selected = faces[0];
  face.struct_size = sizeof(face);
  if (status == EXR_OK) status = exr_font_manager_face(g.font_manager, selected, &face, error);
  if (status == EXR_OK) {
    exr_font_chain_link *chain = NULL; size_t links = 0;
    status = exr_font_manager_chain(g.font_manager, "sans-serif", EXR_FONT_STYLE_REGULAR, &chain, &links, error);
    g.font_fell_back = 0;
    for (size_t i = 0; i < links; i++)
      if (!strcmp(family, "serif") && chain[i].face == selected && chain[i].step == EXR_FONT_STEP_REQUESTED)
        g.font_fell_back = 1;
    exr_free(chain);
    wchar_t *name = host_wide(face.family, strlen(face.family));
    wchar_t *path = host_wide(face.path, strlen(face.path));
    copy_wstring(g.font_family, 128, name ? name : L"");
    copy_wstring(g.font_path, HOST_PATH, path ? path : L"");
    free(name); free(path);
    swprintf(g.font_label, 192, L"正文：%ls%ls", g.font_family, g.font_fell_back ? L"（已回退：无衬线）" : L"");
    OutputDebugStringW(g.font_label); set_status(g.font_label);
    path_join(cache, HOST_PATH, g.data_dir, L"typography.log");
    FILE *log = _wfopen(cache, L"wb");
    if (log) {
      char *label = host_utf8(g.font_label);
      fprintf(log, "%s\nrequested_family=%s\nfamily=%s\nfile=%s\nbody_font=%s\nmanager_ms=%.3f\ncache=%u\nparsed_files=%zu\ncached_files=%zu\nfaces=%zu\n",
        label ? label : "", family, face.family, face.path, strcmp(family, "serif") ? "explicit" : g.font_fell_back ? "fallback-sans" : "serif",
        summary.elapsed_ms, summary.cache, summary.parsed_files, summary.cached_files, count);
      free(label); fclose(log);
    }
  }
  exr_free(faces);
  return status;
}
