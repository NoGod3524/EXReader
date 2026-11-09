/* SPDX-License-Identifier: MIT */
/* Production persistence paths: preserve foreign fields, rollback and anchors. */
static void test_dictionary_storage(void) {
  wchar_t temporary[HOST_PATH],directory[HOST_PATH],good[HOST_PATH],csv[HOST_PATH];
  GetTempPathW(HOST_PATH,temporary);
  swprintf(directory,HOST_PATH,L"%lsexreader-dict-storage-%lu",temporary,(unsigned long)GetCurrentProcessId());
  assert(ensure_directory(directory));copy_wstring(g.data_dir,HOST_PATH,directory);
  path_join(good,HOST_PATH,directory,L"shelf.json");FILE *file=_wfopen(good,L"wb");assert(file);
  fputs("{\"foreign\":{\"count\":7,\"name\":\"preserve\"}}",file);fclose(file);
  dict_init();assert(dict_writable && dict_directory_add(directory) && dict_dir_count==1);
  cv_json *saved=dict_json_load(good,"{}");uint64_t n=0;assert(annot_uint(cv_json_get(saved,"foreign"),"count",&n) && n==7);cv_json_free(saved);
  copy_wstring(dict_path,HOST_PATH,L"Z:\\missing-exreader-test\\shelf.json");
  assert(!dict_directory_remove(0) && dict_dir_count==1 && !wcscmp(dict_dirs[0],directory));
  copy_wstring(dict_path,HOST_PATH,good);
  bounds("Alpha");
  ok(exr_anchor_from_range(select_publication(),&select_range,NULL,&dict_anchor,NULL),NULL);
  dict_word=host_strdup("Alpha");dict_book_title=host_strdup("A book, \"quoted\"");dict_book=g.frame.book_id;
  dict_results=calloc(1,sizeof(*dict_results));assert(dict_results);dict_result_count=1;
  dict_results[0].word=host_strdup("Alpha");dict_results[0].dictionary=host_strdup("Test dictionary");
  dict_results[0].definition=host_strdup("n. meaning, \"quoted\"\nsecond line");
  assert(vocab_add() && vocab_count==1 && strstr(vocab[0].sentence,"Alpha bravo, can't co-operate café."));
  copy_wstring(good,HOST_PATH,vocab_path);copy_wstring(vocab_path,HOST_PATH,L"Z:\\missing-exreader-test\\vocab.json");
  assert(!vocab_add() && vocab_count==1);copy_wstring(vocab_path,HOST_PATH,good);
  path_join(csv,HOST_PATH,directory,L"words.csv");assert(vocab_export(csv));
  file=_wfopen(csv,L"rb");assert(file);char buffer[8192];size_t size=fread(buffer,1,sizeof(buffer)-1,file);fclose(file);buffer[size]=0;
  assert(strstr(buffer,"\"\"quoted\"\"") && strstr(buffer,"例句") && strstr(buffer,"Alpha bravo"));
  cv_text escaped={0};vocab_csv_cell(&escaped,"=1+2,\"x\"\nnext");assert(!strcmp(escaped.data,"\"'=1+2,\"\"x\"\"\nnext\""));cv_text_free(&escaped);
  char *sentence=host_strdup(vocab[0].sentence);dict_shutdown();vocab_load();
  assert(vocab_writable && vocab_count==1 && !strcmp(sentence,vocab[0].sentence));
  char *resolved=dict_sentence(&vocab[0].anchor);assert(resolved && !strcmp(resolved,sentence));free(resolved);free(sentence);
  dict_shutdown();file=_wfopen(good,L"wb");assert(file);fputs("{broken",file);fclose(file);
  vocab_load();assert(!vocab_writable && !vocab_save());
  file=_wfopen(good,L"rb");assert(file);size=fread(buffer,1,sizeof(buffer)-1,file);buffer[size]=0;fclose(file);assert(!strcmp(buffer,"{broken"));
  dict_shutdown();DeleteFileW(good);DeleteFileW(csv);path_join(good,HOST_PATH,directory,L"shelf.json");DeleteFileW(good);RemoveDirectoryW(directory);
  puts("DICTIONARY storage: shelf preservation, rollback, CSV quoting, sentence/anchor restart, corrupt-file preservation PASS");
}
