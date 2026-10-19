/* SPDX-License-Identifier: MIT */
#ifndef EXR_AUDIO_H
#define EXR_AUDIO_H
#include "base.h"
#define EXR_AUDIO_VERSION "0.20.0"
#ifdef __cplusplus
extern "C" {
#endif
/* Immutable host-defined audio timeline. No codec, URI scheme, UI or device is
   assumed. Track order defines concatenation; all timestamps are milliseconds. */
typedef struct exr_audio exr_audio;
typedef struct {
  const char *id,*uri,*media_type;
  uint64_t duration_ms;
} exr_audio_track;
typedef struct {
  const char *id,*title;
  size_t parent; /* SIZE_MAX root; otherwise an earlier containing chapter. */
  uint64_t start_ms,end_ms;
} exr_audio_chapter;
typedef struct {
  const char *part_id; /* Arbitrary host text-part or fixed-page ID. */
  size_t start,end; /* Host UTF-8 byte range, not validated against a document. */
  uint64_t start_ms,end_ms;
} exr_audio_sync;
typedef struct {
  size_t struct_size;
  const char *title;
  const exr_audio_track *tracks; size_t track_count;
  const exr_audio_chapter *chapters; size_t chapter_count;
  const exr_audio_sync *sync; size_t sync_count;
} exr_audio_input;
typedef struct { size_t track; uint64_t offset_ms; } exr_audio_position;
EXR_API exr_status exr_audio_create(const exr_audio_input *input,const exr_control *control,exr_audio **out,exr_error *error);
EXR_API void exr_audio_free(exr_audio *audio);
EXR_API const char *exr_audio_title(const exr_audio *audio);
EXR_API uint64_t exr_audio_duration(const exr_audio *audio);
EXR_API const exr_audio_track *exr_audio_tracks(const exr_audio *audio,size_t *count);
EXR_API const exr_audio_chapter *exr_audio_chapters(const exr_audio *audio,size_t *count);
EXR_API const exr_audio_sync *exr_audio_syncs(const exr_audio *audio,size_t *count);
EXR_API size_t exr_audio_memory_size(const exr_audio *audio);
/* Boundary timestamps choose the next track; total duration chooses final EOF. */
EXR_API exr_status exr_audio_locate(const exr_audio *audio,uint64_t time_ms,exr_audio_position *out,exr_error *error);
/* Enumerate matches in provider order by calling again with from=index+1.
   Misses return SIZE_MAX. Sync intervals are half-open and may overlap. */
EXR_API exr_status exr_audio_sync_at(const exr_audio *audio,uint64_t time_ms,size_t from,const exr_control *control,size_t *index,exr_error *error);
EXR_API exr_status exr_audio_sync_text(const exr_audio *audio,const char *part_id,size_t start,size_t end,size_t from,
                                        const exr_control *control,size_t *index,exr_error *error);

EXR_API exr_status exr_audio_time(const exr_audio *audio,size_t track,uint64_t offset_ms,uint64_t *time_ms,exr_error *error);
typedef struct exr_audio_player exr_audio_player;
typedef enum { EXR_AUDIO_LOAD,EXR_AUDIO_PLAY,EXR_AUDIO_PAUSE,EXR_AUDIO_SEEK,EXR_AUDIO_RATE,EXR_AUDIO_CLOSE } exr_audio_command_kind;
typedef struct {
  exr_audio_command_kind kind;
  size_t track;
  const exr_audio_track *source; /* Borrowed for callback duration. LOAD opens paused. */
  uint64_t offset_ms,generation;
  double rate;
} exr_audio_command;
typedef exr_status (*exr_audio_command_fn)(void *context,const exr_audio_command *command,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_audio_command_fn command;
  void *context;
  void (*release)(void *context);
} exr_audio_backend;
typedef struct {
  uint64_t time_ms,generation;
  exr_audio_position position;
  const char *track_id; /* Borrowed until player_free. */
  double rate;
  int playing,needs_reload;
} exr_audio_playback;
/* Retains audio. Backend context ownership transfers only on success. */
EXR_API exr_status exr_audio_player_create(exr_audio *audio,const exr_audio_backend *backend,exr_audio_player **out,exr_error *error);
EXR_API void exr_audio_player_free(exr_audio_player *player);
EXR_API exr_status exr_audio_player_get(const exr_audio_player *player,exr_audio_playback *out,exr_error *error);
EXR_API exr_status exr_audio_player_play(exr_audio_player *player,exr_error *error);
EXR_API exr_status exr_audio_player_pause(exr_audio_player *player,exr_error *error);
EXR_API exr_status exr_audio_player_seek(exr_audio_player *player,uint64_t time_ms,exr_error *error);
EXR_API exr_status exr_audio_player_rate(exr_audio_player *player,double rate,exr_error *error);
/* Restores paused by stable track ID, so inserting earlier tracks is harmless. */
EXR_API exr_status exr_audio_player_restore(exr_audio_player *player,const char *track_id,uint64_t offset_ms,double rate,exr_error *error);
/* Reports actual backend progress; stale generations and backwards reports are
   rejected. A matching ended report advances tracks or finishes playback. */
EXR_API exr_status exr_audio_player_report(exr_audio_player *player,uint64_t generation,size_t track,uint64_t offset_ms,int ended,exr_error *error);

/* Native RIFF/WAVE random PCM decoding; source ownership transfers on success. */
typedef struct exr_wave exr_wave;
typedef struct {
  uint32_t sample_rate,channels,bits_per_sample,valid_bits,channel_mask;
  uint64_t frames;
  int floating;
} exr_wave_info;
EXR_API exr_status exr_wave_open(const char *path,const exr_control *control,exr_wave **out,exr_error *error);
EXR_API exr_status exr_wave_open_source(const exr_source *source,exr_wave **out,exr_error *error);
EXR_API void exr_wave_free(exr_wave *wave);
EXR_API const exr_wave_info *exr_wave_format(const exr_wave *wave);
/* Interleaved float output, caller capacity >= frames*channels. At most 65536
   frames per call. Runtime error/cancellation zeros output and returns read=0. */
EXR_API exr_status exr_wave_read(exr_wave *wave,uint64_t first_frame,size_t frames,float *output,size_t *read,
                                  const exr_control *control,exr_error *error);
/* Native raw FLAC. Source ownership transfers only on success. Opening reads
   metadata, not the whole audio payload. UINT64_MAX frames means unspecified
   STREAMINFO duration; a read reaching verified EOF resolves the actual length.
   Per-frame CRC8/CRC16 are checked; the whole-stream MD5 is not verified. */
typedef struct exr_flac exr_flac;
typedef struct {
  uint32_t sample_rate,channels,bits_per_sample;
  uint64_t frames;
} exr_flac_info;
EXR_API exr_status exr_flac_open(const char *path,const exr_control *control,exr_flac **out,exr_error *error);
EXR_API exr_status exr_flac_open_source(const exr_source *source,exr_flac **out,exr_error *error);
EXR_API void exr_flac_free(exr_flac *flac);
EXR_API const exr_flac_info *exr_flac_format(const exr_flac *flac);
/* Same float layout, request limit and failure clearing as exr_wave_read.
   Bounded scans may return EXR_LIMIT while retaining verified seek checkpoints. */
EXR_API exr_status exr_flac_read(exr_flac *flac,uint64_t first_frame,size_t frames,float *output,size_t *read,
  const exr_control *control,exr_error *error);
/* Optional minimp3 C codec, independently licensed CC0. Symbols remain present
   with EXR_ENABLE_MP3=OFF; available returns zero and opens return EXR_FORMAT.
   Supports MPEG-1/2/2.5 Layer III with ordinary bitrates, not free-format. */
typedef struct exr_mp3 exr_mp3;
typedef struct { uint32_t sample_rate,channels; uint64_t frames; } exr_mp3_info;
EXR_API int exr_mp3_available(void);
EXR_API exr_status exr_mp3_open(const char *path,const exr_control *control,exr_mp3 **out,exr_error *error);
EXR_API exr_status exr_mp3_open_source(const exr_source *source,exr_mp3 **out,exr_error *error);
EXR_API void exr_mp3_free(exr_mp3 *mp3);
EXR_API const exr_mp3_info *exr_mp3_format(const exr_mp3 *mp3);
/* Gapless sample indices when valid Xing/LAME duration/delay metadata exists;
   otherwise frames may be UINT64_MAX until verified EOF. Uses bounded seeking
   with complete decoder-state checkpoints; runtime failures clear output. */
EXR_API exr_status exr_mp3_read(exr_mp3 *mp3,uint64_t first_frame,size_t frames,float *output,size_t *read,
  const exr_control *control,exr_error *error);

/* Optional FAAD2 C codec, EXR_ENABLE_AAC=OFF by default. Supports ADTS with a
   single raw block and channel_configuration 1..7; no ADIF/LATM or CRC checking.
   Disabled builds retain symbols: available returns zero, opens EXR_FORMAT. */
typedef struct exr_aac exr_aac;
typedef struct { uint32_t sample_rate,channels; uint64_t frames; } exr_aac_info;
EXR_API int exr_aac_available(void);
EXR_API exr_status exr_aac_open(const char *path,const exr_control *control,exr_aac **out,exr_error *error);
EXR_API exr_status exr_aac_open_source(const exr_source *source,exr_aac **out,exr_error *error);
EXR_API void exr_aac_free(exr_aac *aac);
EXR_API const exr_aac_info *exr_aac_format(const exr_aac *aac);
/* Complete ADTS PCM timeline; frames may be UINT64_MAX until EOF. Backward
   seeks replay from the start. Bounded scans return EXR_LIMIT and retain progress
   for retrying the same target. Same request limit/output clearing as wave_read. */
EXR_API exr_status exr_aac_read(exr_aac *aac,uint64_t first_frame,size_t frames,float *output,size_t *read,
  const exr_control *control,exr_error *error);
/* Ordinary unfragmented M4A/M4B mp4a AAC using the same optional codec gate.
   Reads sample tables/packets on demand. Encrypted media, external data refs,
   multiple sample descriptions and discontinuous/rate-changing edits are rejected. */
typedef struct exr_m4b exr_m4b;
typedef struct { uint32_t sample_rate,channels; uint64_t frames; } exr_m4b_info;
EXR_API int exr_m4b_available(void);
EXR_API exr_status exr_m4b_open(const char *path,const exr_control *control,exr_m4b **out,exr_error *error);
EXR_API exr_status exr_m4b_open_source(const exr_source *source,exr_m4b **out,exr_error *error);
EXR_API void exr_m4b_free(exr_m4b *m4b);
EXR_API const exr_m4b_info *exr_m4b_format(const exr_m4b *m4b);
/* Trims priming/tail via supported edit/sample durations, includes leading empty
   edit silence. Accurate backward seeks use bounded replay as in aac_read. */
EXR_API exr_status exr_m4b_read(exr_m4b *m4b,uint64_t first_frame,size_t frames,float *output,size_t *read,
  const exr_control *control,exr_error *error);

/* Format-independent PCM source. Channel ordering is declared by the provider;
   channel_mask==0 leaves it unspecified. frames==UINT64_MAX means unknown.
   Providers return requested frames or fewer only at EOF, with finite samples.
   Context ownership transfers only on successful create. */
typedef struct exr_pcm exr_pcm;
typedef struct { uint32_t sample_rate,channels,channel_mask; uint64_t frames; } exr_pcm_info;
typedef exr_status (*exr_pcm_read_fn)(void *context,uint64_t first_frame,size_t frames,float *output,
  size_t *read,const exr_control *control,exr_error *error);
typedef struct {
  size_t struct_size;
  exr_pcm_info info;
  exr_pcm_read_fn read;
  void *context;
  exr_context_release_fn release;
} exr_pcm_input;
EXR_API exr_status exr_pcm_create(const exr_pcm_input *input,exr_pcm **out,exr_error *error);
/* Auto-detects WAV, FLAC, enabled MP3/ADTS AAC/M4A/M4B, with the same ownership rules. */
EXR_API exr_status exr_pcm_open(const char *path,const exr_control *control,exr_pcm **out,exr_error *error);
EXR_API exr_status exr_pcm_open_source(const exr_source *source,exr_pcm **out,exr_error *error);
EXR_API void exr_pcm_free(exr_pcm *pcm);
EXR_API const exr_pcm_info *exr_pcm_format(const exr_pcm *pcm);
EXR_API exr_status exr_pcm_read(exr_pcm *pcm,uint64_t first_frame,size_t frames,float *output,size_t *read,
  const exr_control *control,exr_error *error);
/* Bounded native WSOLA pitch-preserving time stretch, interleaved float PCM.
   Format stays fixed; rate is playback speed 0.5..2, sample_rate 7350..192000,
   channels 1..8. push accepts available ring capacity, pull returns <= one hop;
   serialize access and retry after draining output when backpressure accepts 0. */
typedef struct exr_stretch exr_stretch;
typedef struct {
  uint32_t sample_rate,channels; double rate;
  uint64_t input_frames,output_frames;
  size_t input_buffered,output_buffered,latency_frames;
  int finished,drained;
} exr_stretch_state;
EXR_API exr_status exr_stretch_create(uint32_t sample_rate,uint32_t channels,double rate,exr_stretch **out,exr_error *error);
EXR_API void exr_stretch_free(exr_stretch *stretch);
EXR_API exr_status exr_stretch_get(const exr_stretch *stretch,exr_stretch_state *out,exr_error *error);
EXR_API exr_status exr_stretch_push(exr_stretch *stretch,const float *input,size_t frames,size_t *accepted,const exr_control *control,exr_error *error);
EXR_API exr_status exr_stretch_pull(exr_stretch *stretch,float *output,size_t frames,size_t *read,const exr_control *control,exr_error *error);
/* finish closes input; pull through drained. Exact duration is round(input/rate)
   using the reported Q32 rate. reset discards the stream and changes its rate. */
EXR_API exr_status exr_stretch_finish(exr_stretch *stretch,exr_error *error);
EXR_API exr_status exr_stretch_reset(exr_stretch *stretch,double rate,exr_error *error);
/* Optional system audio endpoint using the default output device. No engine
   worker thread or automatic file access. The backend name identifies compiled
   support, not device availability; open can fail on a headless system.
   Hosts serialize operations and arrange platform audio-session/lifecycle policy. */
typedef struct exr_audio_output exr_audio_output;
EXR_API const char *exr_audio_output_backend(void);
EXR_API exr_status exr_audio_output_open(uint32_t sample_rate,uint32_t channels,exr_audio_output **out,exr_error *error);
EXR_API void exr_audio_output_free(exr_audio_output *output);
/* Interleaved finite float input, clipped to [-1,1] and converted to PCM16.
   At most 65536 frames per call; written can be smaller or zero (backpressure).
   Open is active: accepted audio starts when queued. Source data is copied.
   Paused writes return written=0; retry unwritten frames when space is available.
   An I/O error may follow partial submission: always honor written even on error. */
EXR_API exr_status exr_audio_output_write(exr_audio_output *output,const float *samples,size_t frames,size_t *written,exr_error *error);
EXR_API exr_status exr_audio_output_pause(exr_audio_output *output,int paused,exr_error *error);
EXR_API exr_status exr_audio_output_flush(exr_audio_output *output,exr_error *error);
/* Approximate queued frames, not a sample-exact playback clock. */
EXR_API exr_status exr_audio_output_pending(exr_audio_output *output,size_t *frames,exr_error *error);
/* Independent ISO-BMFF metadata snapshot, available even with AAC disabled.
   inspect_source borrows the source for this call and never calls release.
   Reads iTunes ilst text/PNG/JPEG cover and Nero chpl or referenced QuickTime text chapters.
   Unknown duration/end is UINT64_MAX. Chapter timestamps use the audio ms model. */
typedef struct exr_m4b_inspection exr_m4b_inspection;
EXR_API exr_status exr_m4b_inspect(const char *path,const exr_control *control,exr_m4b_inspection **out,exr_error *error);
EXR_API exr_status exr_m4b_inspect_source(const exr_source *source,exr_m4b_inspection **out,exr_error *error);
EXR_API void exr_m4b_inspection_free(exr_m4b_inspection *inspection);
EXR_API uint64_t exr_m4b_inspection_duration(const exr_m4b_inspection *inspection);
EXR_API const exr_metadata_entry *exr_m4b_inspection_metadata(const exr_m4b_inspection *inspection,size_t *count);
EXR_API const exr_audio_chapter *exr_m4b_inspection_chapters(const exr_m4b_inspection *inspection,size_t *count);
EXR_API const void *exr_m4b_inspection_cover(const exr_m4b_inspection *inspection,size_t *size,const char **media_type);
#ifdef __cplusplus
}
#endif
#endif
