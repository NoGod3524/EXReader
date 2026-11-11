/* SPDX-License-Identifier: MIT */
#include <exr/audio.h>
#include <stdio.h>

int main(void) {
  const exr_audio_track track = {"track-1", "one.wav", "audio/wav", 1000};
  exr_audio_input input = {0};
  exr_audio *audio = NULL;
  exr_audio_position position = {0};
  exr_error error = {0};
  input.struct_size = sizeof(input);
  input.title = "A host timeline";
  input.tracks = &track;
  input.track_count = 1;
  exr_status status = exr_audio_create(&input, NULL, &audio, &error);
  if (status == EXR_OK) status = exr_audio_locate(audio, 500, &position, &error);
  if (status == EXR_OK)
    printf("track=%zu offset=%llu ms\n", position.track, (unsigned long long)position.offset_ms);
  else fprintf(stderr, "%s\n", error.message);
  /* Timeline creation does not open the URI or start an audio device. */
  exr_audio_free(audio);
  return status == EXR_OK ? 0 : 1;
}
