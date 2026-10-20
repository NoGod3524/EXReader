/* SPDX-License-Identifier: MIT */
/* Deterministic structure-mutating fuzz driver for the memory parsers.
 *
 * No external fuzzing runtime is required: one process mutates seed inputs with
 * a seeded xorshift generator, writes the exact bytes about to be parsed to
 * --save and its parser name to --save.format before parsing. The selected
 * parser follows the seed format even after header bytes are damaged.
 *
 * Usage:
 *   exreader-fuzz --seed 1 --iterations 100000 --save last.bin a.pdf b.epub c.txt
 *   exreader-fuzz --replay last.bin
 *   exreader-fuzz --replay sample.bin --format cbz
 */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#include "exreader.h"
#include <ctype.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#if defined(_WIN32)
#include <io.h>
#include <windows.h>
#else
#include <unistd.h>
#include <time.h>
#endif

typedef struct { unsigned char *data; size_t size; const char *name;exr_format format; } seed;
static const struct { const char *name;exr_format format; } formats[] = {
  {"txt",EXR_TXT},{"html",EXR_HTML},{"xhtml",EXR_HTML},{"fb2",EXR_FB2},
  {"epub",EXR_EPUB},{"docx",EXR_DOCX},{"rtf",EXR_RTF},{"mobi",EXR_MOBI},
  {"azw",EXR_MOBI},{"azw3",EXR_MOBI},{"pdf",EXR_PDF},{"cbz",EXR_CBZ}
};
static exr_format named_format(const char *name) {
  for(size_t i=0;i<sizeof(formats)/sizeof(*formats);i++) {
    const unsigned char *a=(const unsigned char *)name,*b=(const unsigned char *)formats[i].name;
    while(*a && *b && tolower(*a)==*b) { a++;b++; }
    if(!*a && !*b) return formats[i].format;
  }
  return EXR_CUSTOM;
}
static const char *format_name(exr_format format) {
  for(size_t i=0;i<sizeof(formats)/sizeof(*formats);i++) if(formats[i].format==format) return formats[i].name;
  return "auto";
}
static exr_format input_format(const char *name,const unsigned char *data,size_t size) {
  const char *extension=strrchr(name,'.');exr_format format=extension ? named_format(extension+1) : EXR_CUSTOM;
  if(format) return format;
  if(size>=5 && !memcmp(data,"%PDF-",5)) return EXR_PDF;
  if(size>=4 && !memcmp(data,"PK\003\004",4)) return EXR_EPUB;
  return size && data[0]=='<' ? EXR_FB2 : EXR_TXT;
}
/* A shorter next input must remove the previous record's trailing bytes. */
static int save_input(FILE *file,const void *data,size_t size) {
  if(fseek(file,0,SEEK_SET) || fwrite(data,1,size,file)!=size || fflush(file)) return 0;
#if defined(_WIN32)
  return _chsize_s(_fileno(file),(__int64)size)==0;
#else
  return ftruncate(fileno(file),(off_t)size)==0;
#endif
}
/* Integer nanoseconds keep the budget and reported duration in the same units. */
static uint64_t cpu_nanoseconds(void) {
#if defined(_WIN32)
  FILETIME created,exited,kernel,user;ULARGE_INTEGER k,u;
  if(!GetProcessTimes(GetCurrentProcess(),&created,&exited,&kernel,&user)) return UINT64_MAX;
  k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;
  u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
  return (k.QuadPart+u.QuadPart)*100;
#else
  struct timespec value;if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&value)) return UINT64_MAX;
  return (uint64_t)value.tv_sec*1000000000+(uint64_t)value.tv_nsec;
#endif
}

static uint64_t state = 0x9E3779B97F4A7C15u;
static uint64_t next_random(void) {
  uint64_t x = state;
  x ^= x << 13; x ^= x >> 7; x ^= x << 17;
  state = x;
  return x;
}
static size_t below(size_t n) { return n ? (size_t)(next_random() % n) : 0; }

static unsigned char *read_file(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  long n; unsigned char *data;
  if (!f) return NULL;
  if (fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
  data = malloc(n ? (size_t)n : 1);
  if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); fclose(f); return NULL; }
  fclose(f); *size = (size_t)n; return data;
}

/* Parsers accept untrusted bytes; a failed open must always be a clean EXR_* status. */
#ifndef EXR_FUZZ_PROCESS
static exr_status parse(exr_format format,const unsigned char *data, size_t size) {
  exr_error error; exr_document *doc = NULL; exr_fixed_document *fixed = NULL;
  size_t count = 0, i;exr_status status;
  if (format==EXR_PDF || format==EXR_CBZ) {
    status=exr_fixed_open_memory(format,data,size,NULL,&fixed,&error);
    if((status==EXR_OK)!=!!fixed) abort();
    if (fixed) {
      (void)exr_fixed_title(fixed);
      if (exr_fixed_pages(fixed, &count)) {
        for (i = 0; i < count && i < 4; i++) {
          const exr_fixed_page *page = exr_fixed_pages(fixed, &count) + i;
          (void)page->id; (void)page->geometry.bounds[2];
        }
      }
      exr_fixed_free(fixed);
    }
  } else {
    status=exr_document_open_memory(format,data,size,&doc,&error);
    if((status==EXR_OK)!=!!doc) abort();
    if (doc) {
      (void)exr_document_title(doc);
      (void)exr_document_text(doc, &count);
      if (exr_document_chapters(doc, &count)) (void)count;
      if (exr_document_blocks(doc, &count)) (void)count;
      exr_document_free(doc);
    }
  }
  return status;
}
#define EXR_FUZZ_PROCESS parse
#endif
#ifndef EXR_FUZZ_RECORD_NAME
#define EXR_FUZZ_RECORD_NAME format_name
#endif
#ifndef EXR_FUZZ_RECORD_PARSE
#define EXR_FUZZ_RECORD_PARSE named_format
#endif
#ifndef EXR_FUZZ_RESULT_LABEL
#define EXR_FUZZ_RESULT_LABEL "reached a parsed document"
#endif

static void mutate(unsigned char **buf, size_t *size, size_t capacity, const seed *seeds, size_t seed_count) {
  unsigned rounds = 1 + (unsigned)below(8), r;
  for (r = 0; r < rounds; r++) {
    size_t n = *size, at, len;
    unsigned char *b = *buf;
    switch (below(8)) {
      case 0: if (n) b[below(n)] ^= (unsigned char)(1u << below(8)); break;
      case 1: if (n) b[below(n)] = (unsigned char)next_random(); break;
      case 2:
        if (n < capacity) { at = below(n + 1); memmove(b + at + 1, b + at, n - at); b[at] = (unsigned char)next_random(); *size = n + 1; }
        break;
      case 3:
        if (n > 1) { at = below(n); len = 1 + below(n - at); memmove(b + at, b + at + len, n - at - len); *size = n - len; }
        break;
      case 4:
        if (n && n < capacity) { at = below(n); len = 1 + below(n - at); if (len > capacity - n) len = capacity - n;
          memmove(b + at + len, b + at, n - at); memcpy(b + at, b + at + len, len); *size = n + len; }
        break;
      case 5:
        if (n) { at = below(n); len = 1 + below(n - at); memset(b + at, (int)(next_random() & 0xFF), len); }
        break;
      case 6: if (n > 8) *size = 1 + below(n); break;
      default:
        if (seed_count && n) {
          const seed *s = &seeds[below(seed_count)];
          at = below(n); len = s->size ? 1 + below(s->size) : 0;
          if (len > capacity - at) len = capacity - at;
          if (len) memcpy(b + at, s->data + (s->size > len ? below(s->size - len) : 0), len);
        }
        break;
    }
  }
}

static int argument_number(const char *text,uint64_t *out) {
  char *end;unsigned long long value;
  if(!*text || *text<'0' || *text>'9') return 0;
  errno=0;value=strtoull(text,&end,10);if(errno || *end) return 0;
  *out=(uint64_t)value;return 1;
}
int main(int argc, char **argv) {
  seed *seeds; size_t seed_count = 0, capacity = 1u << 20, size, i;
  unsigned char *buf=NULL; const char *save = "fuzz-last.bin",*replay=NULL;char metadata[4096];exr_format forced=EXR_CUSTOM;
  uint64_t iterations=10000,parsed_count=0,iteration,attempts[EXR_CBZ+1]={0},success[EXR_CBZ+1]={0};
  uint64_t cpu_budget=0,cpu_start=0,cpu_end=0;int explicit_iterations=0;
  FILE *sink=NULL,*type_file=NULL;
  int a,result=2;
  seeds = calloc((size_t)argc + 1, sizeof(*seeds));
  if (!seeds) { fprintf(stderr, "fuzz: allocation failed\n"); return 2; }
  for (a = 1; a < argc; a++) {
    if((!strcmp(argv[a],"--seed") || !strcmp(argv[a],"--iterations") || !strcmp(argv[a],"--max-bytes") || !strcmp(argv[a],"--cpu-seconds")) && a+1<argc) {
      const char *option=argv[a++];uint64_t number;
      if(!argument_number(argv[a],&number)) { fprintf(stderr,"fuzz: invalid numeric argument\n");goto done; }
      if(!strcmp(option,"--seed")) state=number|1u;
      else if(!strcmp(option,"--iterations")) { iterations=number;explicit_iterations=1; }
      else if(!strcmp(option,"--cpu-seconds")) { if(!number || number>UINT64_MAX/1000000000) { fprintf(stderr,"fuzz: invalid CPU duration\n");goto done; }cpu_budget=number; }
      else { if(!number || number>SIZE_MAX) { fprintf(stderr,"fuzz: invalid byte limit\n");goto done; }capacity=(size_t)number; }
      continue;
    }
    if (!strcmp(argv[a], "--save") && a + 1 < argc) { save = argv[++a]; continue; }
    if (!strcmp(argv[a], "--replay") && a + 1 < argc) { replay=argv[++a];continue; }
    if (!strcmp(argv[a], "--format") && a + 1 < argc) {
      forced=EXR_FUZZ_RECORD_PARSE(argv[++a]);if(!forced) { fprintf(stderr,"fuzz: unknown format %s\n",argv[a]);goto done; }continue;
    }
    if (argv[a][0] == '-') { fprintf(stderr, "fuzz: unknown option %s\n", argv[a]);goto done; }
    seeds[seed_count].name = argv[a];
    seeds[seed_count].data = read_file(argv[a], &seeds[seed_count].size);
    if (!seeds[seed_count].data) { fprintf(stderr, "fuzz: cannot read %s\n", argv[a]);goto done; }
    seed_count++;
  }
  if(replay) {
    exr_format format;exr_status status;char type[16];
    buf=read_file(replay,&size);if(!buf) { fprintf(stderr,"fuzz: cannot read %s\n",replay);goto done; }
    if(!forced) {
      int n=snprintf(metadata,sizeof(metadata),"%s.format",replay);
      if(n<0 || (size_t)n>=sizeof(metadata)) goto done;
      type_file=fopen(metadata,"rb");
      if(type_file) {
        size_t nread=fread(type,1,sizeof(type)-1,type_file);int more=fgetc(type_file),failed=ferror(type_file);
        if(fclose(type_file)) failed=1;
        type_file=NULL;
        if(memchr(type,0,nread)) failed=1;
        while(nread && (type[nread-1]=='\r' || type[nread-1]=='\n')) nread--;
        type[nread]=0;forced=EXR_FUZZ_RECORD_PARSE(type);
        if(failed || more!=EOF || !forced) { fprintf(stderr,"fuzz: invalid replay format record\n");goto done; }
      } else if(errno!=ENOENT) { fprintf(stderr,"fuzz: cannot read replay format record\n");goto done; }
    }
    format=forced ? forced : input_format(replay,buf,size);status=EXR_FUZZ_PROCESS(format,buf,size);
    printf("replay: format=%s bytes=%zu status=%d\n",EXR_FUZZ_RECORD_NAME(format),size,(int)status);
    result=0;goto done;
  }
  if (!seed_count || !iterations) { fprintf(stderr, "fuzz: need at least one seed file and non-zero iterations\n");goto done; }
  buf = malloc(capacity);
  if (!buf) { fprintf(stderr, "fuzz: allocation failed\n");goto done; }
  sink = fopen(save, "wb");
  if (!sink) { fprintf(stderr, "fuzz: cannot create %s\n", save);goto done; }
  { int n=snprintf(metadata,sizeof(metadata),"%s.format",save);
    if(n<0 || (size_t)n>=sizeof(metadata)) goto done;
  }
  type_file=fopen(metadata,"wb");if(!type_file) { fprintf(stderr,"fuzz: cannot create format record\n");goto done; }
  cpu_start=cpu_nanoseconds();if(cpu_start==UINT64_MAX) { fprintf(stderr,"fuzz: process CPU clock unavailable\n");goto done; }
  if(cpu_budget && !explicit_iterations) iterations=UINT64_MAX;
  for(i=0;i<seed_count;i++) seeds[i].format=forced ? forced : input_format(seeds[i].name,seeds[i].data,seeds[i].size);
  for (iteration=0;iteration<iterations;iteration++) {
    if(cpu_budget) {
      uint64_t now=cpu_nanoseconds();if(now==UINT64_MAX || now<cpu_start) { fprintf(stderr,"fuzz: process CPU clock failed\n");goto done; }
      if(now-cpu_start>=cpu_budget*1000000000) break;
    }
    const seed *base = &seeds[below(seed_count)];
    size = base->size < capacity ? base->size : capacity;
    memcpy(buf, base->data, size);
    mutate(&buf, &size, capacity, seeds, seed_count);
    /* Keep the exact bytes on disk before parsing so a crash is reproducible. */
    if(!save_input(sink,buf,size) || !save_input(type_file,EXR_FUZZ_RECORD_NAME(base->format),strlen(EXR_FUZZ_RECORD_NAME(base->format)))) {
      fprintf(stderr,"fuzz: cannot persist triggering input and format\n");goto done;
    }
    attempts[base->format]++;
    if(EXR_FUZZ_PROCESS(base->format,buf,size)==EXR_OK) { parsed_count++;success[base->format]++; }
    if ((iteration+1)%10000==0) fprintf(stderr,"fuzz: %" PRIu64 " iterations, %" PRIu64 " parsed\n",iteration+1,parsed_count);
  }
  cpu_end=cpu_nanoseconds();if(cpu_end==UINT64_MAX || cpu_end<cpu_start) { fprintf(stderr,"fuzz: invalid process CPU clock\n");goto done; }
  printf("fuzz: %" PRIu64 " iterations over %zu seeds, %" PRIu64 " " EXR_FUZZ_RESULT_LABEL ", no crash\n",
         iteration, seed_count, parsed_count);
  printf("process_cpu_seconds=%" PRIu64 ".%09" PRIu64 " requested_cpu_seconds=%" PRIu64 "\n",
         (cpu_end-cpu_start)/1000000000,(cpu_end-cpu_start)%1000000000,cpu_budget);
  for(unsigned format=EXR_TXT;format<=EXR_CBZ;format++) if(attempts[format])
    printf("format=%s attempts=%" PRIu64 " parsed=%" PRIu64 "\n",EXR_FUZZ_RECORD_NAME((exr_format)format),attempts[format],success[format]);
  result=0;
done:
  if(sink && fclose(sink)) result=2;
  if(type_file && fclose(type_file)) result=2;
  for (i = 0; i < seed_count; i++) free(seeds[i].data);
  free(seeds); free(buf);
  return result;
}
