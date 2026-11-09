/* Exercise non-document fixture formats through the public SDK. */
#include "exreader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    exr_error error = {0};
    exr_status status = EXR_ARGUMENT;
    size_t processed = 0;
    if (argc != 3) return 2;
    if (!strcmp(argv[1], "image")) {
        FILE *file = fopen(argv[2], "rb");
        long size;
        void *data;
        exr_bitmap bitmap = {0};
        if (!file || fseek(file, 0, SEEK_END) || (size = ftell(file)) < 0) return 3;
        rewind(file);
        data = malloc(size ? (size_t)size : 1);
        if (!data || fread(data, 1, (size_t)size, file) != (size_t)size) return 3;
        fclose(file);
        status = exr_image_decode(data, (size_t)size, &bitmap, &error);
        if (status == EXR_OK) processed = 1;
        exr_bitmap_free(&bitmap);
        free(data);
    } else if (!strcmp(argv[1], "font")) {
        exr_font *font = NULL;
        status = exr_font_open(argv[2], &font, &error);
        processed = exr_font_count(font);
        exr_font_free(font);
    } else if (!strcmp(argv[1], "library")) {
        exr_library *library = NULL;
        status = exr_library_open(argv[2], &library, &error);
        exr_library_close(library);
    } else if (!strcmp(argv[1], "configuration")) {
        exr_font_manager *manager = NULL;
        status = exr_font_manager_open(argv[2], &manager, &error);
        exr_font_manager_free(manager);
    } else if (!strcmp(argv[1], "audio_metadata")) {
        exr_m4b_inspection *inspection = NULL;
        status = exr_m4b_inspect(argv[2], NULL, &inspection, &error);
        exr_m4b_inspection_free(inspection);
    } else if (!strcmp(argv[1], "audio")) {
        exr_pcm *pcm = NULL;
        status = exr_pcm_open(argv[2], NULL, &pcm, &error);
        if (status == EXR_OK) {
            const exr_pcm_info *info = exr_pcm_format(pcm);
            float *samples = malloc(4096 * info->channels * sizeof(float));
            if (!samples) return 3;
            while (processed < info->frames && status == EXR_OK) {
                size_t count = 0, want = info->frames-processed < 4096 ? (size_t)(info->frames-processed) : 4096;
                status = exr_pcm_read(pcm, processed, want, samples, &count, NULL, &error);
                if (status == EXR_OK && !count) { free(samples); exr_pcm_free(pcm); return 4; }
                processed += count;
            }
            free(samples);
        }
        exr_pcm_free(pcm);
    } else if (!strcmp(argv[1], "sevenz")) {
        exr_sevenz *archive = NULL;
        status = exr_sevenz_open(argv[2], NULL, &archive, &error);
        if (status == EXR_OK) {
            size_t count = 0;
            const exr_sevenz_entry *entries = exr_sevenz_entries(archive, &count);
            for (size_t i = 0; i < count && status == EXR_OK; i++) {
                void *data = NULL;
                size_t size = 0;
                if (entries[i].is_directory) continue;
                status = exr_sevenz_extract(archive, i, &data, &size, &error);
                if (status == EXR_OK) processed++;
                exr_free(data);
            }
        }
        exr_sevenz_free(archive);
    } else return 2;
    printf("{\"status\":%d,\"processed\":%zu}\n", (int)status, processed);
    return 0;
}
