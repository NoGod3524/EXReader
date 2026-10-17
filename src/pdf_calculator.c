/* SPDX-License-Identifier: GPL-3.0-only */
#include "pdf_calculator_internal.h"
enum {
  PUSH_INT,PUSH_REAL,BR_FALSE,JUMP,
  ABS,ADD,ATAN,CEILING,COS,CVI,CVR,DIV,EXP,FLOOR,IDIV,LN,LOG,MOD,MUL,
  NEG,ROUND,SIN,SQRT,SUB,TRUNCATE,AND,BITSHIFT,EQ,FALSE,GE,GT,LE,LT,NE,
  NOT,OR,TRUE,XOR,COPY,DUP,EXCH,INDEX,POP,ROLL
};
/* Operator names follow PDF 32000-1 table 42 / Adobe PLRM third edition.
   Copyright 1985-1999 Adobe Systems Incorporated. See THIRD_PARTY_NOTICES.md. */
static const struct { const char *name; unsigned op; } operators[]={
  {"abs",ABS},{"add",ADD},{"atan",ATAN},{"ceiling",CEILING},{"cos",COS},
  {"cvi",CVI},{"cvr",CVR},{"div",DIV},{"exp",EXP},{"floor",FLOOR},
  {"idiv",IDIV},{"ln",LN},{"log",LOG},{"mod",MOD},{"mul",MUL},
  {"neg",NEG},{"round",ROUND},{"sin",SIN},{"sqrt",SQRT},{"sub",SUB},
  {"truncate",TRUNCATE},{"and",AND},{"bitshift",BITSHIFT},{"eq",EQ},
  {"false",FALSE},{"ge",GE},{"gt",GT},{"le",LE},{"lt",LT},{"ne",NE},
  {"not",NOT},{"or",OR},{"true",TRUE},{"xor",XOR},{"copy",COPY},
  {"dup",DUP},{"exch",EXCH},{"index",INDEX},{"pop",POP},{"roll",ROLL}
};
typedef struct { double value; unsigned op,target; } instruction;
struct exr_pdf_calculator { size_t count,cost; exr_control control; instruction code[]; };
typedef struct {
  const unsigned char *source; size_t size,at,count,cost;
  instruction *code; const exr_control *control; exr_error *error;
} compiler;
static int space(unsigned char c) { return !c || c==9 || c==10 || c==12 || c==13 || c==32; }
static void skip(compiler *c) {
  while(c->at<c->size) {
    if(space(c->source[c->at])) c->at++;
    else if(c->source[c->at]=='%') { while(c->at<c->size && c->source[c->at]!=10 && c->source[c->at]!=13) c->at++; }
    else break;
  }
}
static int delimiter(unsigned char c) { return space(c) || strchr("{}()<>[]/%",c)!=NULL; }
static size_t token(compiler *c) {
  size_t start=c->at; while(c->at<c->size && !delimiter(c->source[c->at])) c->at++; return c->at-start;
}
static int word(compiler *c,const char *name) {
  size_t start,n; skip(c); start=c->at; n=token(c); return n==strlen(name) && !memcmp(c->source+start,name,n);
}
static exr_status emit(compiler *c,unsigned op,double value,size_t *index) {
  size_t cost=(op==COPY || op==ROLL) ? 100 : (op==ATAN || op==COS || op==EXP || op==LN || op==LOG || op==SIN || op==SQRT) ? 32 : 1;
  if(c->count==4096) return exr_fail(c->error,EXR_LIMIT,"PDF calculator exceeds 4096 instructions");
  if(!(c->count&255) && exr_control_cancel(c->control,c->error)!=EXR_OK) return EXR_CANCELLED;
  if(index) *index=c->count;
  if(c->code) c->code[c->count]=(instruction){value,op,0};
  c->count++; c->cost+=cost; return EXR_OK;
}
static int literal(const unsigned char *s,size_t n,double *value,unsigned *op) {
  size_t i=0,digits=0; int negative=0,point=0; double v=0,fraction=.1;
  if(i<n && (s[i]=='+' || s[i]=='-')) negative=s[i++]=='-';
  for(;i<n;i++) {
    if(s[i]=='.' && !point) { point=1; continue; }
    if(s[i]<'0' || s[i]>'9') return 0;
    digits++;
    if(point) { v+=(s[i]-'0')*fraction; fraction*=.1; } else v=v*10+s[i]-'0';
    if(!isfinite(v)) return 0;
  }
  if(!digits) return 0;
  *value=negative ? -v : v; *op=!point && *value>=INT32_MIN && *value<=INT32_MAX ? PUSH_INT : PUSH_REAL; return 1;
}
/* Braced conditional expressions are syntax, never stack procedure objects. */
static exr_status block(compiler *c,unsigned depth) {
  if(depth>32) return exr_fail(c->error,EXR_LIMIT,"PDF calculator exceeds 32 nested blocks");
  for(;;) {
    size_t start,n,i,branch=0,jump=0; unsigned op; double value;
    skip(c); if(c->at==c->size) break;
    if(c->source[c->at]=='}') { c->at++; return EXR_OK; }
    if(c->source[c->at]=='{') {
      c->at++; if(emit(c,BR_FALSE,0,&branch)!=EXR_OK || block(c,depth+1)!=EXR_OK) return c->error->code;
      skip(c);
      if(c->at<c->size && c->source[c->at]=='{') {
        c->at++; if(emit(c,JUMP,0,&jump)!=EXR_OK) return c->error->code;
        if(c->code) c->code[branch].target=(unsigned)c->count;
        if(block(c,depth+1)!=EXR_OK) return c->error->code;
        if(c->code) c->code[jump].target=(unsigned)c->count;
        if(!word(c,"ifelse")) break;
      } else {
        if(c->code) c->code[branch].target=(unsigned)c->count;
        if(!word(c,"if")) break;
      }
      continue;
    }
    start=c->at; n=token(c); if(!n) break;
    if(literal(c->source+start,n,&value,&op)) { if(emit(c,op,value,NULL)!=EXR_OK) return c->error->code; continue; }
    for(i=0;i<sizeof(operators)/sizeof(*operators);i++) if(n==strlen(operators[i].name) && !memcmp(c->source+start,operators[i].name,n)) break;
    if(i==sizeof(operators)/sizeof(*operators)) break;
    if(emit(c,operators[i].op,0,NULL)!=EXR_OK) return c->error->code;
  }
  return exr_fail(c->error,EXR_FORMAT,"Invalid PDF calculator syntax or operator");
}
exr_status exr_pdf_calculator_open(const unsigned char *source,size_t size,const exr_control *control,exr_pdf_calculator **out,exr_error *error) {
  compiler c={0}; exr_pdf_calculator *p=NULL; unsigned pass; exr_error local={0}; exr_status status;
  *out=NULL; c.source=source; c.size=size; c.control=control; c.error=error ? error : &local;
  if(size>65536) return exr_fail(error,EXR_LIMIT,"PDF calculator source exceeds 64 KiB");
  for(pass=0;pass<2;pass++) {
    if(exr_control_cancel(control,c.error)!=EXR_OK) { status=EXR_CANCELLED; goto fail; }
    c.at=c.count=c.cost=0; skip(&c);
    if(c.at==size || source[c.at++]!='{') { status=exr_fail(c.error,EXR_FORMAT,"PDF calculator requires outer braces"); goto fail; }
    status=block(&c,0); if(status!=EXR_OK) goto fail;
    skip(&c); if(c.at!=size) { status=exr_fail(c.error,EXR_FORMAT,"Trailing PDF calculator source"); goto fail; }
    if(!pass) {
      p=calloc(1,sizeof(*p)+c.count*sizeof(instruction));
      if(!p) { status=exr_fail(c.error,EXR_MEMORY,"PDF calculator allocation failed"); goto fail; }
      p->count=c.count; p->cost=c.cost; if(control) p->control=*control; c.code=p->code;
    }
  }
  *out=p; return EXR_OK;
fail:
  free(p); return status;
}
void exr_pdf_calculator_free(exr_pdf_calculator *p) { free(p); }
size_t exr_pdf_calculator_memory(const exr_pdf_calculator *p) { return sizeof(*p)+p->count*sizeof(instruction); }
size_t exr_pdf_calculator_cost(const exr_pdf_calculator *p) { return p->cost; }
enum { INTEGER,REAL,BOOLEAN };
typedef struct { double value; unsigned type; } operand;
static operand real(double value) { operand v={value,REAL}; return v; }
static operand integer(int64_t value) { operand v={(double)value,INTEGER}; return v; }
static operand boolean(int value) { operand v={value!=0,BOOLEAN}; return v; }
static operand bits(uint32_t value) { return integer(value<=INT32_MAX ? (int64_t)value : (int64_t)value-INT64_C(4294967296)); }
exr_status exr_pdf_calculator_eval_inputs(const exr_pdf_calculator *p,const double *inputs,unsigned input_count,unsigned outputs,double out[4],exr_error *error) {
  operand stack[100]; size_t count=input_count,pc=0,steps=0,i;
  if(!p || !inputs || !input_count || input_count>32 || !outputs || outputs>4 || !out) return exr_fail(error,EXR_ARGUMENT,"Invalid PDF calculator inputs/outputs");
  for(i=0;i<count;i++) { if(!isfinite(inputs[i])) goto invalid; stack[i]=real(inputs[i]); }
  while(pc<p->count) {
    const instruction *ins=p->code+pc++; unsigned op=ins->op; operand a,b,result; double x,y,z=0; int64_t n,j;
    if(++steps%256==0 && exr_control_cancel(&p->control,error)!=EXR_OK) return EXR_CANCELLED;
    if(op==JUMP) { pc=ins->target; continue; }
    if(op==PUSH_INT || op==PUSH_REAL || op==TRUE || op==FALSE) {
      if(count==100) goto limit;
      stack[count++]=op==TRUE || op==FALSE ? boolean(op==TRUE) : op==PUSH_INT ? integer((int64_t)ins->value) : real(ins->value); continue;
    }
    if(!count) goto invalid;
    if(op==BR_FALSE) { a=stack[--count]; if(a.type!=BOOLEAN) goto invalid; if(!a.value) pc=ins->target; continue; }
    if(op==POP) { count--; continue; }
    if(op==DUP) { if(count==100) goto limit; stack[count]=stack[count-1]; count++; continue; }
    if(op==EXCH) { if(count<2) goto invalid; a=stack[count-1]; stack[count-1]=stack[count-2]; stack[count-2]=a; continue; }
    if(op==COPY || op==INDEX || op==ROLL) {
      if(stack[count-1].type!=INTEGER) goto invalid;
      j=(int64_t)stack[--count].value;
      if(op==ROLL) { if(!count || stack[count-1].type!=INTEGER) goto invalid; n=(int64_t)stack[--count].value; } else n=j;
      if(n<0 || (uint64_t)n>count || (op==INDEX && (uint64_t)n==count)) goto invalid;
      if(op==COPY) { if((size_t)n>100-count) goto limit; for(i=0;i<(size_t)n;i++) stack[count+i]=stack[count-(size_t)n+i]; count+=(size_t)n; }
      else if(op==INDEX) { if(count==100) goto limit; a=stack[count-1-(size_t)n]; stack[count++]=a; }
      else if(n) {
        operand temp[100]; j%=n; if(j<0) j+=n;
        memcpy(temp,stack+count-(size_t)n,(size_t)n*sizeof(*temp));
        for(i=0;i<(size_t)n;i++) stack[count-(size_t)n+(i+(size_t)j)%(size_t)n]=temp[i];
      }
      continue;
    }
    a=stack[--count]; x=a.value; result=a;
    if(op==NOT) { if(a.type==BOOLEAN) result=boolean(!x); else if(a.type==INTEGER) result=bits(~(uint32_t)(int32_t)x); else goto invalid; }
    else if(op==ABS || op==CEILING || op==COS || op==CVI || op==CVR || op==FLOOR || op==LN || op==LOG || op==NEG || op==ROUND || op==SIN || op==SQRT || op==TRUNCATE) {
      if(a.type==BOOLEAN) goto invalid;
      switch(op) {
        case ABS: z=fabs(x); break;
        case CEILING: z=ceil(x); break;
        case COS: z=cos(fmod(x,360)*0.01745329251994329577); result.type=REAL; break;
        case CVI: z=trunc(x); if(z<INT32_MIN || z>INT32_MAX) goto invalid; result.type=INTEGER; break;
        case CVR: z=x; result.type=REAL; break;
        case FLOOR: z=floor(x); break;
        case LN: if(x<=0) goto invalid; z=log(x); result.type=REAL; break;
        case LOG: if(x<=0) goto invalid; z=log10(x); result.type=REAL; break;
        case NEG: z=-x; break;
        /* PLRM ties go to the greater integer, including negative halves. */
        case ROUND: z=floor(x); if(x-z>=.5) z+=1; break;
        case SIN: z=sin(fmod(x,360)*0.01745329251994329577); result.type=REAL; break;
        case SQRT: if(x<0) goto invalid; z=sqrt(x); result.type=REAL; break;
        default: z=trunc(x); break;
      }
      result.value=z; if(result.type==INTEGER && (z<INT32_MIN || z>INT32_MAX)) result.type=REAL;
    } else {
      if(!count) goto invalid;
      b=a; y=x; a=stack[--count]; x=a.value;
      if(op==EQ || op==NE) { int equal=(a.type==BOOLEAN)==(b.type==BOOLEAN) && x==y; result=boolean(op==EQ ? equal : !equal); }
      else if(op==AND || op==OR || op==XOR) {
        if(a.type!=b.type || a.type==REAL) goto invalid;
        if(a.type==BOOLEAN) result=boolean(op==AND ? x && y : op==OR ? x || y : (x!=0)!=(y!=0));
        else { uint32_t u=(uint32_t)(int32_t)x,v=(uint32_t)(int32_t)y; result=bits(op==AND ? u&v : op==OR ? u|v : u^v); }
      } else {
        if(a.type==BOOLEAN || b.type==BOOLEAN) goto invalid;
        if(op==GE || op==GT || op==LE || op==LT) result=boolean(op==GE ? x>=y : op==GT ? x>y : op==LE ? x<=y : x<y);
        else if(op==IDIV || op==MOD || op==BITSHIFT) {
          if(a.type!=INTEGER || b.type!=INTEGER) goto invalid;
          n=(int64_t)x; j=(int64_t)y;
          if(op==BITSHIFT) { uint32_t u=(uint32_t)(int32_t)x; result=bits(j<=-32 || j>=32 ? 0 : j<0 ? u>>(unsigned)-j : u<<(unsigned)j); }
          else { if(!j || (op==IDIV && n==INT32_MIN && j==-1)) goto invalid; result=integer(op==IDIV ? n/j : n%j); }
        } else {
          result.type=REAL;
          switch(op) {
            case ADD: z=x+y; break;
            case SUB: z=x-y; break;
            case MUL: z=x*y; break;
            case DIV: if(!y) goto invalid; z=x/y; break;
            case EXP: if((x<0 && y!=floor(y)) || (!x && y<0)) goto invalid; z=pow(x,y); break;
            case ATAN: if(!x && !y) goto invalid; z=atan2(x,y)*57.295779513082320877; if(z<0) z+=360; break;
            default: goto invalid;
          }
          result.value=z;
          if((op==ADD || op==SUB || op==MUL) && a.type==INTEGER && b.type==INTEGER && z>=INT32_MIN && z<=INT32_MAX) result.type=INTEGER;
        }
      }
    }
    if(!isfinite(result.value)) goto invalid;
    stack[count++]=result;
  }
  if(count!=outputs) goto invalid;
  for(i=0;i<count;i++) { if(stack[i].type==BOOLEAN) goto invalid; out[i]=stack[i].value; }
  return EXR_OK;
limit:
  return exr_fail(error,EXR_LIMIT,"PDF calculator exceeds 100 operands");
invalid:
  return exr_fail(error,EXR_FORMAT,"Invalid PDF calculator operands or arithmetic result");
}
exr_status exr_pdf_calculator_eval(const exr_pdf_calculator *p,double input,unsigned outputs,double out[4],exr_error *error) {
  return exr_pdf_calculator_eval_inputs(p,&input,1,outputs,out,error);
}
