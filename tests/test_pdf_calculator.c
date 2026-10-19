/* SPDX-License-Identifier: MIT */
#include "pdf_calculator_internal.h"
static unsigned checks; static exr_error error;
#define CHECK(x) do { checks++; if(!(x)) { fprintf(stderr,"calculator line %d: %s (%d %s)\n",__LINE__,#x,error.code,error.message); exit(1); } } while(0)
static exr_status compile(const char *source,const exr_control *control,exr_pdf_calculator **p) {
  memset(&error,0,sizeof(error)); return exr_pdf_calculator_open((const unsigned char *)source,strlen(source),control,p,&error);
}
static void expression(const char *body,double expected) {
  char source[2048]; exr_pdf_calculator *p=NULL; double out[4];
  snprintf(source,sizeof(source),"{ pop %s }",body);
  if(compile(source,NULL,&p)!=EXR_OK || exr_pdf_calculator_eval(p,.5,1,out,&error)!=EXR_OK) { fprintf(stderr,"expression: %s\n",body); CHECK(0); }
  CHECK(fabs(out[0]-expected)<=1e-12*fmax(1,fabs(expected))); exr_pdf_calculator_free(p);
}
static void expressions(void) {
  static const struct { const char *body; double value; } cases[]={
    {"-3 abs",3},{"-2147483648 abs",2147483648.0},{"2147483647 1 add",2147483648.0},
    {"-2147483648 1 sub",-2147483649.0},{"65536 65536 mul",4294967296.0},
    {"2 3 add 2 idiv",2},{"6 2 sub 3 idiv",1},{"3 2 mul 4 idiv",1},
    {"-2147483648 neg",2147483648.0},{"-2147483648 neg neg cvi",-2147483648.0},
    {"-.5 ceiling",0},{"-.5 floor",-1},{"-.5 truncate",0},{"-6.5 round",-6},{".5 round",1},{"-.5 round",0},
    {"2 ceiling 2 idiv",1},{"-3 floor 2 idiv",-1},{"3 round 2 idiv",1},{"-3 truncate 2 idiv",-1},
    {"270 cos",0},{"450 sin",1},{"-90 sin",-1},{"-180 cos",-1},
    {"1 0 atan",90},{"0 -1 atan",180},{"-1 0 atan",270},{"1 1 atan",45},
    {"1 ln",0},{"100 log",2},{"9 sqrt",3},{"9 .5 exp",3},{"-2 3 exp",-8},
    {"0 0 exp",1},{"3 2 div",1.5},{"-5 2 idiv",-2},{"-5 2 mod",-1},
    {"5 -2 mod",1},{"-2147483648 -1 mod",0},
    {"-3.8 cvi 2 idiv",-1},{"2 cvr .5 add",2.5},{"-.25 neg",.25},
    {"6 3 and",2},{"4 3 or",7},{"6 3 xor",5},{"0 not",-1},
    {"-1 -1 bitshift",2147483647},{"1 31 bitshift",-2147483648.0},
    {"-1 32 bitshift",0},{"-1 -32 bitshift",0},{"-1 -2147483648 bitshift",0},
    {"-1 2147483647 bitshift",0},{"3 -1 bitshift",1},{"-2147483648 0 bitshift",-2147483648.0},
    {"true false and { 1 } { 0 } ifelse",0},{"true false or { 1 } { 0 } ifelse",1},
    {"true true xor { 1 } { 0 } ifelse",0},{"false not { 1 } { 0 } ifelse",1},
    {"1 1.0 eq { 1 } { 0 } ifelse",1},{"true 1 eq { 1 } { 0 } ifelse",0},
    {"false 0 ne { 1 } { 0 } ifelse",1},{"false false eq { 1 } { 0 } ifelse",1},
    {"2 1 ge { 1 } { 0 } ifelse",1},{"2 2 gt { 1 } { 0 } ifelse",0},
    {"2 2 le { 1 } { 0 } ifelse",1},{"1 2 lt { 1 } { 0 } ifelse",1},
    {"1 true { 2 add } if",3},{"1 false { 0 div } if",1},
    {"false { 0 0 div } { .75 } ifelse",.75},
    {"true { true { .25 } { 0 0 div } ifelse } { 0 0 div } ifelse",.25},
    {"2 dup mul",4},{"1 2 exch sub",1},{"1 2 3 1 index add add add",8},
    {"1 2 2 copy add add add",6},{"1 0 copy",1},{"1 2 2 0 roll add",3},
    {"1 2 3 3 1 roll pop exch pop",1},{"1 2 3 3 -1 roll pop exch pop",3},
    {"1 2 3 3 2147483647 roll pop exch pop",1},
    {"1 2 3 3 -2147483648 roll pop exch pop",1},
    {"1 pop 2",2},{"+0002 -0001 add",1},{".25 +.25 add",.5},{"1. 2. add",3},
    {"% comment\r\n .5 % next\n",.5}
  };
  size_t i; for(i=0;i<sizeof(cases)/sizeof(*cases);i++) expression(cases[i].body,cases[i].value);
  { exr_pdf_calculator *p=NULL; double out[4]; CHECK(compile("{ dup 1 exch sub exch dup }",NULL,&p)==EXR_OK);
    CHECK(exr_pdf_calculator_eval(p,.25,3,out,&error)==EXR_OK && out[0]==.75 && out[1]==.25 && out[2]==.25); exr_pdf_calculator_free(p); }
}
static void invalid(void) {
  const char *syntax[]={"", "pop 1", "{} extra", "{", "{ { 1 } }", "{ true { 1 } ifelse }", "{ true { 1 } { 2 } if }",
    "{ if }", "{ ifelse }", "{ 1e2 }", "{ 16#FF }", "{ /x }", "{ (hi) }", "{ [1] }", "{ . }", "{ + }", "{ 1..2 }", "{ loop }", "{ 1 } }"};
  const char *runtime[]={"{pop}","{pop pop}","{true}","{dup}","{1 {pop} if}","{true 1 add}","{true neg}","{true false gt}",
    "{1 true and}","{1.0 2 and}","{1.0 not}","{1.0 1 bitshift}","{1 1.0 bitshift}","{5.5 2 idiv}","{5 2.0 mod}",
    "{0 div}","{pop 1 0 idiv}","{pop 1 0 mod}","{pop -2147483648 -1 idiv}","{pop -1 .5 exp}","{pop 0 -1 exp}",
    "{pop -1 sqrt}","{pop 0 ln}","{pop -1 log}","{pop 0 0 atan}","{pop 2147483648 cvi}","{pop -2147483649 cvi}",
    "{pop 2147483648 2 idiv}","{pop 2147483647 1 add 2 idiv}","{pop -2147483648 abs 2 idiv}","{1 cvr 1 idiv}",
    "{pop -1 index}","{0 index pop pop}","{2 copy}","{.0 copy}","{1.0 -1 roll}","{-1 0 roll}","{2 0 roll}","{pop exch}","{pop 2 1024 exp}"};
  size_t i; for(i=0;i<sizeof(syntax)/sizeof(*syntax);i++) { exr_pdf_calculator *p=(void *)1; CHECK(compile(syntax[i],NULL,&p)==EXR_FORMAT && !p); }
  for(i=0;i<sizeof(runtime)/sizeof(*runtime);i++) { exr_pdf_calculator *p=NULL; double out[4]; CHECK(compile(runtime[i],NULL,&p)==EXR_OK);
    if(exr_pdf_calculator_eval(p,.5,1,out,&error)!=EXR_FORMAT) { fprintf(stderr,"expected runtime error: %s\n",runtime[i]); CHECK(0); }
    checks++; exr_pdf_calculator_free(p); }
}
typedef struct { unsigned calls,after; } cancellation;
static int cancelled(void *context) { cancellation *c=context; return ++c->calls>c->after; }
static void limits(void) {
  char *source=malloc(70000); size_t i,at; exr_pdf_calculator *p=NULL; double out[4];
  cancellation c={0,0}; exr_control control={0}; control.context=&c; control.cancelled=cancelled;
  CHECK(source); CHECK(compile("{ 1 add }",&control,&p)==EXR_CANCELLED && !p);
  c.calls=0; CHECK(compile("{ }",&control,&p)==EXR_CANCELLED && !p);
  { const char *program="{ dup .5 lt { 2 mul } { 1 exch sub } ifelse }";
    for(i=0;i<strlen(program);i++) { memcpy(source,program,i); source[i]=0; CHECK(compile(source,NULL,&p)==EXR_FORMAT && !p); }
  }
  memset(source,' ',65537); source[65537]=0; CHECK(compile(source,NULL,&p)==EXR_LIMIT && !p);
  at=0; source[at++]='{'; for(i=0;i<33;i++) { memcpy(source+at,"true {",6); at+=6; }
  for(i=0;i<33;i++) { memcpy(source+at,"} if ",5); at+=5; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_LIMIT && !p);
  at=0; source[at++]='{'; for(i=0;i<32;i++) { memcpy(source+at,"true {",6); at+=6; }
  for(i=0;i<32;i++) { memcpy(source+at,"} if ",5); at+=5; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_OK); exr_pdf_calculator_free(p);
  at=0; source[at++]='{'; for(i=0;i<4097;i++) { memcpy(source+at," dup",4); at+=4; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_LIMIT && !p);
  source[at-5]='}'; source[at-4]=0;
  CHECK(compile(source,NULL,&p)==EXR_OK); exr_pdf_calculator_free(p);
  at=0; source[at++]='{'; for(i=0;i<100;i++) { memcpy(source+at," dup",4); at+=4; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_OK); CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_LIMIT); exr_pdf_calculator_free(p);
  at=0; source[at++]='{'; for(i=0;i<99;i++) { memcpy(source+at," dup",4); at+=4; }
  for(i=0;i<99;i++) { memcpy(source+at," pop",4); at+=4; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_OK); CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_OK && out[0]==.5); exr_pdf_calculator_free(p);
  at=0; source[at++]='{'; for(i=0;i<97;i++) { memcpy(source+at," dup",4); at+=4; }
  memcpy(source+at," 3 copy }",10); CHECK(compile(source,NULL,&p)==EXR_OK);
  CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_LIMIT); exr_pdf_calculator_free(p);
  CHECK(compile("{ 99 copy }",NULL,&p)==EXR_OK); CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_FORMAT); exr_pdf_calculator_free(p);
  at=0; source[at++]='{'; for(i=0;i<2047;i++) { memcpy(source+at," 0 copy",7); at+=7; } source[at++]='}'; source[at]=0;
  CHECK(compile(source,NULL,&p)==EXR_OK); CHECK(exr_pdf_calculator_cost(p)==2047*101);
  CHECK(exr_pdf_calculator_memory(p)<70000); CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_OK && out[0]==.5); exr_pdf_calculator_free(p);
  c=(cancellation){0,3}; CHECK(compile(source,&control,&p)==EXR_CANCELLED && !p);
  c=(cancellation){0,100}; CHECK(compile(source,&control,&p)==EXR_OK); c.calls=100;
  CHECK(exr_pdf_calculator_eval(p,.5,1,out,&error)==EXR_CANCELLED); exr_pdf_calculator_free(p); free(source);
}
static void multiple_inputs(void) {
  exr_pdf_calculator *p=NULL; double inputs[32]={.25,.5},out[4]; char source[1024]="{"; unsigned i;
  CHECK(compile("{ sub }",NULL,&p)==EXR_OK);
  CHECK(exr_pdf_calculator_eval_inputs(p,inputs,2,1,out,&error)==EXR_OK && out[0]==-.25);
  CHECK(exr_pdf_calculator_eval_inputs(p,inputs,0,1,out,&error)==EXR_ARGUMENT);
  CHECK(exr_pdf_calculator_eval_inputs(p,inputs,33,1,out,&error)==EXR_ARGUMENT);
  inputs[0]=NAN;CHECK(exr_pdf_calculator_eval_inputs(p,inputs,2,1,out,&error)==EXR_FORMAT);exr_pdf_calculator_free(p);inputs[0]=.25;
  for(i=1;i<32;i++) strcat(source," pop");
  strcat(source," }");
  CHECK(compile(source,NULL,&p)==EXR_OK);
  CHECK(exr_pdf_calculator_eval_inputs(p,inputs,32,1,out,&error)==EXR_OK && out[0]==.25);exr_pdf_calculator_free(p);
  strcpy(source,"{");for(i=0;i<69;i++) strcat(source," 0");strcat(source," }");
  CHECK(compile(source,NULL,&p)==EXR_OK);CHECK(exr_pdf_calculator_eval_inputs(p,inputs,32,1,out,&error)==EXR_LIMIT);exr_pdf_calculator_free(p);
}
int main(void) { expressions(); invalid(); limits(); multiple_inputs(); printf("%u PDF calculator checks passed\n",checks); return 0; }
