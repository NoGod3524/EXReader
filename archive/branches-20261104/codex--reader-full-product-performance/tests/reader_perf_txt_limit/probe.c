/* Public SDK diagnostic: contrast TXT line count with file size. */
#include <exreader.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int run(size_t lines, size_t line_bytes, exr_status expected) {
  const size_t size = lines * (line_bytes + 1);
  char *data = (char *)malloc(size);
  exr_document *document = NULL;
  exr_error error = {0};
  if (!data) return 0;
  for (size_t i = 0; i < lines; i++) {
    memset(data + i * (line_bytes + 1), 'a', line_bytes);
    data[i * (line_bytes + 1) + line_bytes] = '\n';
  }
  exr_status status = exr_document_open_memory(EXR_TXT, data, size, &document, &error);
  printf("{\"lines\":%zu,\"line_bytes\":%zu,\"input_bytes\":%zu,\"status\":%d,\"expected\":%d,\"message\":\"%s\"}\n",
         lines, line_bytes, size, (int)status, (int)expected, error.message);
  exr_document_free(document);
  free(data);
  return status == expected;
}

int main(void) {
  int ok = 1;
  ok &= run(131070, 64, EXR_OK);
  ok &= run(131071, 64, EXR_OK);
  ok &= run(131072, 64, EXR_LIMIT);
  ok &= run(10000, 1700, EXR_OK);
  return ok ? 0 : 1;
}
