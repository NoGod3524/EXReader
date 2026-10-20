/* SPDX-License-Identifier: MIT */
#define main fuzz_driver_main
#include "fuzz_parse.c"
#undef main
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(1); } } while(0)
int main(int argc,char **argv) {
  unsigned char long_record[4096],short_record[3]={0,255,7},readback[4096];size_t size;FILE *file;char path[4096];uint64_t value;
  CHECK(argc==2);memset(long_record,42,sizeof(long_record));file=tmpfile();CHECK(file);
  CHECK(save_input(file,long_record,sizeof(long_record)));CHECK(save_input(file,short_record,sizeof(short_record)));
  CHECK(!fseek(file,0,SEEK_SET));CHECK(fread(readback,1,sizeof(readback),file)==sizeof(short_record));CHECK(!memcmp(readback,short_record,sizeof(short_record)));
  CHECK(!ferror(file) && feof(file));CHECK(save_input(file,short_record,0));CHECK(!fseek(file,0,SEEK_END) && ftell(file)==0);CHECK(!fclose(file));
  snprintf(path,sizeof(path),"%s/comic.cbz",argv[1]);unsigned char *bytes=read_file(path,&size);CHECK(bytes);
  file=fopen(path,"rb");CHECK(file);CHECK(!save_input(file,short_record,sizeof(short_record)));CHECK(!fclose(file));
  CHECK(input_format("BOOK.CBZ",bytes,size)==EXR_CBZ);CHECK(parse(EXR_CBZ,bytes,size)==EXR_OK);
  CHECK(parse(EXR_EPUB,bytes,size)!=EXR_OK);free(bytes);
  /* The 908-byte sample that stalled the 200k campaign: its central directory
     understates one entry's compressed size while the local header is intact.
     Extraction must end in an explicit error instead of spinning. */
  snprintf(path,sizeof(path),"%s/fuzz-cbz-truncated.bin",argv[1]);
  bytes=read_file(path,&size);CHECK(bytes);
  CHECK(parse(EXR_CBZ,bytes,size)==EXR_FORMAT);free(bytes);
  CHECK(input_format("book.docx",(const unsigned char *)"bad",3)==EXR_DOCX);
  CHECK(input_format("book.pdf",(const unsigned char *)"bad",3)==EXR_PDF);
  CHECK(input_format("last.bin",(const unsigned char *)"%PDF-",5)==EXR_PDF);
  CHECK(parse(EXR_PDF,(const unsigned char *)"bad",3)!=EXR_OK);
  CHECK(parse(EXR_TXT,(const unsigned char *)"",0)==EXR_ARGUMENT);
  CHECK(named_format("XHTML")==EXR_HTML && named_format("azw3")==EXR_MOBI && !named_format("auto"));
  CHECK(argument_number("18446744073709551615",&value) && value==UINT64_MAX);
  CHECK(!argument_number("18446744073709551616",&value));CHECK(!argument_number("-1",&value));CHECK(!argument_number("5x",&value));
  printf("%u fuzz driver checks passed\n",checks);return 0;
}
