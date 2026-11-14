/* SPDX-License-Identifier: MIT */
#define main reflow_regression_main
#include "test_docx_reflow.c"
#undef main

int main(int argc,char **argv) {
  const size_t sizes[]={1,100,200,1000};size_t k,t,pos,violations=0;
  CHECK(argc==2);OK(exr_font_open(argv[1],&font,&error));
  setvbuf(stdout,NULL,_IONBF,0);
  puts("paragraphs position incremental_p50_ms full_p50_ms ratio incremental_max_ms max_key_ratio");
  for(k=0;k<4;k++) for(pos=0;pos<3;pos++) {
    size_t count=sizes[k],index=pos==0 ? 0 : pos==1 ? count/2 : count-1;
    exr_edit_doc *doc=model(count,0);exr_pager *p=pager(doc);
    double inc_max=0,ratio_max=0,incs[31],fulls[31];
    for(t=0;t<31;t++) {
      size_t n;double start,inc,full;exr_pager *fresh;
#ifdef _WIN32
      ULONG64 inc_begin,inc_end,full_begin,full_end;
#endif
      const exr_edit_block *b=exr_edit_block_at(doc,index);exr_edit_id id=b->id;
      char text[128];snprintf(text,sizeof(text),"%.*sx",(int)b->runs[0].text_size,b->runs[0].text);
      OK(exr_edit_set_run_text(doc,id,0,text,strlen(text)));
#ifdef _WIN32
      CHECK(QueryThreadCycleTime(GetCurrentThread(),&inc_begin));
#endif
      start=now();OK(exr_edit_layout_after(doc,p,id,&n,&error));inc=(now()-start)*1000;
#ifdef _WIN32
      CHECK(QueryThreadCycleTime(GetCurrentThread(),&inc_end));
      CHECK(QueryThreadCycleTime(GetCurrentThread(),&full_begin));
#endif
      start=now();fresh=pager(doc);full=(now()-start)*1000;
#ifdef _WIN32
      CHECK(QueryThreadCycleTime(GetCurrentThread(),&full_end));
#endif
      CHECK(exr_edit_reflow_statistics(p).page_count==exr_edit_reflow_statistics(fresh).page_count);
      exr_pager_free(fresh);
      if(inc>inc_max) inc_max=inc;
      if(inc/full>ratio_max) ratio_max=inc/full;
      incs[t]=inc;fulls[t]=full;
      if(count>=200 && inc>=full*.1) {
        fprintf(stderr,"key %zu: %zu paragraphs, position %zu: %.6f / %.6f ms (%.2f%%)\n",
          t,count,index,inc,full,100*inc/full);
#ifdef _WIN32
        fprintf(stderr,"thread cycles: %llu / %llu (%.2f%%)\n",
          (unsigned long long)(inc_end-inc_begin),(unsigned long long)(full_end-full_begin),
          100.0*(inc_end-inc_begin)/(full_end-full_begin));
#endif
        violations++;
      }
    }
    qsort(incs,31,sizeof(double),double_order);qsort(fulls,31,sizeof(double),double_order);
    printf("%zu %s %.6f %.6f %.6f %.6f %.6f\n",count,pos==0 ? "start" : pos==1 ? "middle" : "end",incs[15],fulls[15],incs[15]/fulls[15],inc_max,ratio_max);
    if(count>=200) CHECK(incs[15]<fulls[15]*.1);
    compare(p,doc);exr_pager_free(p);exr_edit_doc_free(doc);
  }
  basic();insertions();convergence();history();failures();formatting();unicode();anchors();
  long_paragraph();anchor_revisions();empty();disjoint();
  exr_font_free(font);CHECK(violations==0);
  puts("l08-reflow-perf: passed");return 0;
}
