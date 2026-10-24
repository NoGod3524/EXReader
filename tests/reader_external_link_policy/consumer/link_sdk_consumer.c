/* SPDX-License-Identifier: MIT */
/* Installed C consumer that joins the two public packages the way a host does:
   the frozen reading SDK supplies authored navigation (href plus base), the link
   policy decides between INTERNAL and NEEDS_HOST, and only INTERNAL targets are
   handed back to the SDK resolver. No book or URL parser is reimplemented here;
   the assertion is that both components draw the same boundary. */
#include "reader_link_policy.h"
#include "exreader.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures;

static void verdict(const char* name, int ok) {
  if (!ok) failures++;
  printf("CHK\t%s\t%s\n", name, ok ? "ok" : "bad");
}

int main(int argc, char** argv) {
  exr_document* document = NULL;
  exr_navigation* navigation = NULL;
  size_t count = 0, i, chapters = 0;
  size_t internal = 0, fragments = 0, external = 0, resolved = 0, refused = 0;
  int baseline = 0;
  reader_link_policy* policy = NULL;
  exr_error error;

  if (argc != 2) {
    fprintf(stderr, "usage: link-sdk-consumer <epub>\n");
    return 2;
  }
  memset(&error, 0, sizeof(error));
  if (exr_document_open(argv[1], &document, &error) != EXR_OK || !document) {
    fprintf(stderr, "FATAL\topen failed: %s\n", error.message);
    return 2;
  }
  if (reader_link_policy_create(NULL, &policy, NULL) != READER_LINK_OK) {
    fprintf(stderr, "FATAL\tpolicy create failed\n");
    return 2;
  }
  verdict("sdk-open", 1);
  if (exr_document_navigation(document, &navigation, &count, &error) != EXR_OK) {
    fprintf(stderr, "FATAL\tnavigation failed: %s\n", error.message);
    return 2;
  }
  (void)exr_document_chapters(document, &chapters);
  printf("CHK\tsdk-navigation-count\t%zu\t%zu\n", count, chapters);
  if (count < 4 || chapters == 0) failures++;

  for (i = 0; i < count; i++) {
    const exr_navigation* entry = &navigation[i];
    reader_link_result result;
    size_t chapter, resource = SIZE_MAX, node = SIZE_MAX;
    exr_status status;
    if (!entry->href || !*entry->href) continue;
    if (!entry->base || !*entry->base) {
      printf("CHK\tsdk-navigation-base\tbad\n");
      failures++;
      break;
    }
    if (!baseline) {
      printf("CHK\tsdk-navigation-base\t%s\n", entry->base);
      baseline = 1;
    }
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    if (reader_link_classify(policy, entry->href, strlen(entry->href), entry->base, NULL,
                             &result, NULL) != READER_LINK_OK) {
      failures++;
      continue;
    }
    chapter = entry->part < chapters ? entry->part : 0;
    status = exr_document_resolve(document, chapter, entry->href, &resource, &node, &error);
    if (result.action == READER_LINK_ACTION_NEEDS_HOST) {
      external++;
      /* The SDK must refuse what the policy sends to the host. */
      if (status == EXR_ARGUMENT) refused++;
      else {
        printf("CHK\tsdk-external-agreement\tbad\n");
        failures++;
      }
    } else if (result.action == READER_LINK_ACTION_INTERNAL) {
      internal++;
      if (result.flags & READER_LINK_FLAG_HAS_FRAGMENT) fragments++;
      /* The SDK must accept every internal target the policy keeps in the book. */
      if (status == EXR_OK) resolved++;
      else {
        printf("CHK\tsdk-internal-handoff-failed\t%s\t%d\n", entry->href, (int)status);
        failures++;
      }
    } else {
      printf("CHK\tsdk-unexpected-reject\t%s\t%s\n", entry->href,
             reader_link_reason_name(result.reason));
      failures++;
    }
    reader_link_result_free(&result);
  }

  printf("CHK\tsdk-internal-resolved\t%zu\t%zu\t%zu\n", internal, resolved, fragments);
  printf("CHK\tsdk-external-refused\t%zu\t%zu\n", external, refused);
  if (internal < 3 || resolved != internal || fragments < 2) failures++;
  if (external < 1 || refused != external) failures++;

  {
    /* A CFI is handed to the public CFI API, never parsed by the policy. */
    reader_link_result result;
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    reader_link_classify(policy, "#epubcfi(/6/4[chap01ref]!/4[body01]/10[para05]/3:10)",
                         strlen("#epubcfi(/6/4[chap01ref]!/4[body01]/10[para05]/3:10)"), NULL, NULL,
                         &result, NULL);
    verdict("sdk-cfi-kind",
            result.action == READER_LINK_ACTION_INTERNAL && result.kind == READER_LINK_KIND_CFI &&
                result.path_len == 0);
    reader_link_result_free(&result);
  }
  {
    /* A scheme the policy rejects is also refused by the resolver. */
    reader_link_result result;
    size_t resource = SIZE_MAX, node = SIZE_MAX;
    memset(&result, 0, sizeof(result));
    result.struct_size = (uint32_t)sizeof(result);
    reader_link_classify(policy, "custom:resource#time=90", strlen("custom:resource#time=90"),
                         NULL, NULL, &result, NULL);
    verdict("sdk-unknown-scheme-agreement",
            result.action == READER_LINK_ACTION_REJECT &&
                result.reason == READER_LINK_REASON_UNKNOWN_SCHEME &&
                exr_document_resolve(document, 0, "custom:resource#time=90", &resource, &node,
                                     &error) != EXR_OK);
    reader_link_result_free(&result);
  }

  reader_link_policy_destroy(policy);
  exr_navigation_free(navigation, count);
  exr_document_free(document);
  if (failures) {
    printf("sdk-consumer-failed %d\n", failures);
    return 1;
  }
  printf("sdk-consumer-ok\n");
  return 0;
}
