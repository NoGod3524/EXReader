/* SPDX-License-Identifier: MIT */
static int tts_dump(const char *name) {
  cv_text j={0};long rate=999;unsigned long native_state=0,native_stream=0;size_t native_offset=0;
  shell_speech_get_rate(tts_voice,&rate);shell_speech_status(tts_voice,&native_state,&native_stream,&native_offset);
  cv_text_format(&j,"{\"state\":%d,\"native_state\":%lu,\"stream\":%lu,\"native_stream\":%lu,\"rate\":%ld,\"voice\":%d,\"events\":%lu,\"jumps\":%lu,\"chunks\":%lu,\"minimized\":%d,\"position\":[%llu,%llu],\"page\":%llu,\"frame\":[%llu,%llu,%llu],",
    tts_state,native_state,tts_stream,native_stream,rate,tts_voice_index,tts_events,tts_jumps,tts_chunks,IsIconic(g.window),
    (unsigned long long)tts_position.part,(unsigned long long)tts_position.offset,(unsigned long long)g.frame.page,
    (unsigned long long)g.frame.part,(unsigned long long)g.frame.range_start,(unsigned long long)g.frame.range_end);
  cv_text_format(&j,"\"uptime_ms\":%llu,\"native_offset\":%llu,",(unsigned long long)GetTickCount64(),(unsigned long long)native_offset);
  char *message=host_utf8(tts_message);annot_json_string(&j,"message",message);free(message);
  cv_text_string(&j,",\"voices\":[");
  for(size_t i=0;i<shell_speech_count(tts_voice);i++) {
    char *voice=host_utf8(shell_speech_name(tts_voice,i));if(i) cv_text_string(&j,",");cv_text_json(&j,voice);free(voice);
  }
  cv_text_string(&j,"],\"sentence\":");
  if(tts_sentence<tts_chunk.sentence_count) {
    exr_text_range r=tts_chunk.sentences[tts_sentence].range;
    HRGN region=select_region_for(r.start.offset,r.end.offset);RECT box;int visible=r.start.part==g.frame.part && GetRgnBox(region,&box)!=NULLREGION;DeleteObject(region);
    cv_text_format(&j,"{\"start\":%llu,\"end\":%llu,\"visible\":%d}",(unsigned long long)r.start.offset,(unsigned long long)r.end.offset,visible);
  } else cv_text_string(&j,"null");
  cv_text_string(&j,"}\n");int ok=!j.failed && select_drive_write(name,".tts.json",j.data,j.size);cv_text_free(&j);return ok;
}
static int tts_drive(const char *action) {
  if(!strcmp(action,"tts_dump")) return tts_dump(drive_args[1]);
  if(!strcmp(action,"tts_open")) {tts_command(100);return tts_voice!=NULL;}
  if(!strcmp(action,"tts_close")) {tts_command(104);return 1;}
  if(!strcmp(action,"tts_start")) {tts_command(101);return tts_state==1;}
  if(!strcmp(action,"tts_pause")) {tts_pause(1);return tts_state==2;}
  if(!strcmp(action,"tts_resume")) {tts_pause(0);return tts_state==1;}
  if(!strcmp(action,"tts_stop")) {tts_command(103);return tts_state==0;}
  if(!strcmp(action,"tts_rate")) return tts_set_rate(atoi(drive_args[1]));
  if(!strcmp(action,"tts_voice")) return tts_set_voice(atoi(drive_args[1]));
  if(!strcmp(action,"tts_minimize")) {ShowWindow(g.window,SW_MINIMIZE);return 1;}
  if(!strcmp(action,"tts_restore")) {ShowWindow(g.window,SW_SHOWNOACTIVATE);return 1;}
  if(!strcmp(action,"tts_no_voices")) {tts_start();return !tts_state && wcsstr(tts_message,L"没有可用")!=NULL;}
  return 0;
}
