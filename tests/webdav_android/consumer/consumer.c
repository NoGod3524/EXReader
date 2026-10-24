/* SPDX-License-Identifier: MIT */
/* This file is compiled as C11 and sees only the installed public C ABI. */
#include "exr_webdav.h"
#include "consumer.h"
#include <pthread.h>
#include <stdio.h>
#include <string.h>
struct control_state { exr_webdav_client *client;uint64_t received,cancel;int reenter,reentry; };
static int cancelled(void *opaque){struct control_state *s=opaque;return s->received>=s->cancel;}
static void progress(void *opaque,uint64_t received){
  struct control_state *s=opaque;s->received=received;
  if(s->reenter&&!s->reentry){
    exr_webdav_listing out={0};exr_webdav_error error={0};
    s->reentry=exr_webdav_list(s->client,"",NULL,&out,&error);
    exr_webdav_listing_free(&out);exr_webdav_free(s->client);
  }
}
struct wrong_state {exr_webdav_client *client;int status;};
static void *wrong(void *opaque){
  struct wrong_state *s=opaque;exr_webdav_listing out={0};exr_webdav_error error={0};
  s->status=exr_webdav_list(s->client,"",NULL,&out,&error);exr_webdav_listing_free(&out);exr_webdav_free(s->client);return NULL;
}
void dav_consume(const char *root,const char *auth,const char *directory,const char *action,
  const char *resource,const char *filename,const uint64_t limits[6],struct dav_result *result){
  exr_webdav_config config={root,auth,limits[0],(size_t)limits[1],(size_t)limits[2],(unsigned)limits[3]};
  exr_webdav_client *client=NULL;exr_webdav_error error={0};exr_webdav_listing listing={0};exr_webdav_download download={0};
  struct control_state state={NULL,0,limits[4],!strcmp(action,"reentry"),0};
  exr_webdav_control control={cancelled,progress,&state};memset(result,0,sizeof(*result));
  result->status=exr_webdav_create(&config,&client,&error);if(result->status)goto done;
  state.client=client;
  if(!strcmp(action,"owner")){
    pthread_t worker;struct wrong_state other={client,0};
    if(pthread_create(&worker,NULL,wrong,&other)!=0){result->status=EXR_DAV_IO;goto done;}
    pthread_join(worker,NULL);result->wrong_owner=other.status;
  }
  if(!strcmp(action,"list")||!strcmp(action,"owner")){
    result->status=exr_webdav_list(client,resource,&control,&listing,&error);result->count=listing.count;
    if(listing.count){snprintf(result->resource,sizeof(result->resource),"%s",listing.entries[0].resource);snprintf(result->title,sizeof(result->title),"%s",listing.entries[0].display_name);}
  }else if(!strcmp(action,"mkcol"))result->status=exr_webdav_make_collection(client,resource,&control,&error);
  else if(!strcmp(action,"put")){
    char file[4096];snprintf(file,sizeof(file),"%s/source.bin",directory);
    result->status=exr_webdav_publish_file(client,resource,file,limits[5],&control,&error);
  }else{
    result->status=exr_webdav_download_file(client,resource,directory,filename,&control,&download,&error);
    result->bytes=download.bytes;result->published=download.published;
  }
done:
  result->http=error.http_status;result->reentry=state.reentry;
  exr_webdav_listing_free(&listing);exr_webdav_free(client);
}
