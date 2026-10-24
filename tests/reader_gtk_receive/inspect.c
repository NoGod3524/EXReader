/* SPDX-License-Identifier: MIT */
/* Actions-only installed public SDK readback; the actual host is closed first. */
#include <exr/library.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
int main(int argc,char **argv) {
  if(argc!=4) return 2;
  int result=1;int64_t id=(int64_t)strtoll(argv[2],NULL,10);exr_library *library=NULL;
  exr_error error={0};exr_source source={0};exr_book *books=NULL;size_t count=0,notes=0,position=0;
  FILE *output=NULL;
  if(exr_library_open(argv[1],&library,&error)!=EXR_OK ||
     exr_library_books(library,"",&books,&count,&error)!=EXR_OK) goto done;
  size_t index=0;while(index<count && books[index].id!=id) index++;
  if(index==count) goto done;position=books[index].position;
  if(books[index].format==EXR_EPUB) {
    exr_epub_note *rows=NULL;if(exr_library_epub_notes(library,id,&rows,&notes,&error)!=EXR_OK) goto done;
    exr_epub_notes_free(rows,notes);
  } else if(books[index].format==EXR_PDF || books[index].format==EXR_CBZ) {
    exr_fixed_note *rows=NULL;if(exr_library_fixed_notes(library,id,&rows,&notes,&error)!=EXR_OK) goto done;
    exr_fixed_notes_free(rows,notes);
  } else {
    exr_note *rows=NULL;if(exr_library_notes(library,id,&rows,&notes,&error)!=EXR_OK) goto done;
    exr_notes_free(rows,notes);
  }
  if(exr_library_source(library,id,&source,&error)!=EXR_OK || !(output=fopen(argv[3],"wb"))) goto done;
  unsigned char bytes[65536];size_t offset=0;
  while(offset<source.size) {
    size_t amount=source.size-offset;if(amount>sizeof(bytes)) amount=sizeof(bytes);
    if(source.read_at(source.context,offset,bytes,amount)!=amount || fwrite(bytes,1,amount,output)!=amount) goto done;
    offset+=amount;
  }
  if(fclose(output)) { output=NULL;goto done; }output=NULL;
  printf("{\"book\":%"PRId64",\"bytes\":%zu,\"notes\":%zu,\"position\":%zu}\n",id,source.size,notes,position);result=0;
done:
  if(output) fclose(output);
  if(source.release) source.release(source.context);
  exr_books_free(books,count);exr_library_close(library);return result;
}
