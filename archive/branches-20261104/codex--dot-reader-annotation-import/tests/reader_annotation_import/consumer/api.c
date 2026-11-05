#include <reader_annotation_import.h>
int main(void){reader_annotation_import_stats s={0};reader_annotation_import_error e={0};return reader_annotation_import_run(0,&s,&e)==READER_AI_ARGUMENT&&s.committed==0&&s.complete_product_accepted==0?0:1;}
