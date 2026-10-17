/* SPDX-License-Identifier: GPL-3.0-only */
#include "internal.h"
#include <ctype.h>
enum { BOLD, ITALIC, SIZE, COLOR, BACKGROUND, UNDERLINE, STRIKE, ALIGN, LEFT, RIGHT,
       INDENT, BEFORE, AFTER, LEADING, MULTIPLE, DIRECTION, RTF_PROPERTIES };
typedef struct { int skip,uc,destination; int properties[RTF_PROPERTIES]; } rtf_state;
typedef struct {
  exr_document *doc;
  exr_buffer run;
  rtf_state style;
  size_t paragraph,body;
  uint32_t colors[4096];
  size_t color_count;
  unsigned red,green,blue,components;
  exr_status status;
  exr_error *error;
} rtf_context;
static int put(exr_buffer *b,const char *s) { return exr_append(b,s,strlen(s)); }
static size_t make(rtf_context *c,size_t parent,exr_node_kind kind,const char *tag,const char *text) {
  size_t at=exr_model_html(c->doc,parent,0,kind,tag,text);
  if(at==SIZE_MAX) c->status=EXR_LIMIT;
  return at;
}
static int set(rtf_context *c,size_t node,const char *key,const char *value) {
  if(!exr_model_attribute(c->doc,node,key,value)) { c->status=EXR_LIMIT; return 0; } return 1;
}
static int css_number(exr_buffer *b,const char *name,float value,int px) {
  char text[100]; snprintf(text,sizeof(text),"%s:%.4f%s;",name,value,px ? "px" : ""); return put(b,text);
}
static int paragraph_style(rtf_context *c,const rtf_state *s) {
  exr_buffer css={0}; const int *p=s->properties; int ok;
  if(c->paragraph==SIZE_MAX) return 1;
  ok=put(&css,p[ALIGN]==1 ? "text-align:right;" : p[ALIGN]==2 ? "text-align:center;" : p[ALIGN]==3 ? "text-align:justify;" : "text-align:left;") &&
      css_number(&css,"margin-left",p[LEFT]/15.0f,1) && css_number(&css,"margin-right",p[RIGHT]/15.0f,1) &&
      css_number(&css,"text-indent",p[INDENT]/15.0f,1) && css_number(&css,"margin-top",p[BEFORE]/15.0f,1) &&
      css_number(&css,"margin-bottom",p[AFTER]/15.0f,1);
  if(ok && p[LEADING]) ok=css_number(&css,"line-height",fabsf((float)p[LEADING])/(p[MULTIPLE] ? 240.0f : 15.0f),!p[MULTIPLE]);
  if(ok && p[DIRECTION]) ok=put(&css,p[DIRECTION]==1 ? "direction:ltr;" : "direction:rtl;");
  ok=ok && set(c,c->paragraph,"style",css.data); free(css.data); return ok;
}
static int paragraph(rtf_context *c,const rtf_state *s) {
  if(c->paragraph==SIZE_MAX) {
    c->paragraph=make(c,c->body,EXR_NODE_PARAGRAPH,"p",NULL); if(c->paragraph==SIZE_MAX) return 0;
  }
  return paragraph_style(c,s);
}
static int css_color(rtf_context *c,exr_buffer *b,const char *property,int index) {
  uint32_t color; char text[100];
  if(!index) return 1;
  if(index<0 || (size_t)index>=c->color_count) { c->status=EXR_FORMAT; return 0; }
  color=c->colors[index]; if(!color) return 1;
  snprintf(text,sizeof(text),"%s:#%06lx;",property,(unsigned long)(color>>8)); return put(b,text);
}
static int run_flush(rtf_context *c) {
  const int *p=c->style.properties; exr_buffer css={0}; size_t parent,span; int ok=0;
  if(!c->run.size) return 1;
  if(!paragraph(c,&c->style)) goto done;
  parent=c->paragraph;
  if(p[BOLD]) { parent=make(c,parent,EXR_NODE_ELEMENT,"strong",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[ITALIC]) { parent=make(c,parent,EXR_NODE_ELEMENT,"em",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[UNDERLINE]) { parent=make(c,parent,EXR_NODE_ELEMENT,"u",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[STRIKE]) { parent=make(c,parent,EXR_NODE_ELEMENT,"s",NULL); if(parent==SIZE_MAX) goto done; }
  if(p[SIZE] && !css_number(&css,"font-size",p[SIZE]*2.0f/3,1)) goto done;
  if(!css_color(c,&css,"color",p[COLOR]) || !css_color(c,&css,"background-color",p[BACKGROUND])) goto done;
  span=make(c,parent,EXR_NODE_ELEMENT,"span",NULL);
  if(span==SIZE_MAX || (css.size && !set(c,span,"style",css.data)) || make(c,span,EXR_NODE_TEXT,NULL,c->run.data)==SIZE_MAX) goto done;
  c->run.size=0; if(c->run.data) c->run.data[0]=0; ok=1;
done:
  free(css.data); if(!ok && c->status==EXR_OK) c->status=EXR_LIMIT; return ok;
}
static int emit(rtf_context *c,const rtf_state *s,uint32_t cp) {
  if(s->skip || s->destination) return 1;
  if(c->run.size && memcmp(c->style.properties,s->properties,sizeof(s->properties)) && !run_flush(c)) return 0;
  if(!c->run.size) c->style=*s;
  if(!exr_codepoint(&c->run,cp)) { c->status=EXR_LIMIT; return 0; } return 1;
}
static int literal(rtf_context *c,const rtf_state *s,uint32_t cp) {
  if(s->skip) return 1;
  if(s->destination==1) {
    if(cp==';') {
      if(c->color_count>=4096) { c->status=EXR_LIMIT; return 0; }
      c->colors[c->color_count++]=c->components ? (c->red<<24)|(c->green<<16)|(c->blue<<8)|255u : 0;
      c->red=c->green=c->blue=c->components=0;
    }
    return 1;
  }
  return emit(c,s,cp);
}
static int line_break(rtf_context *c,const rtf_state *s,int soft) {
  if(!run_flush(c)) return 0;
  if(soft) {
    if(!paragraph(c,s) || make(c,c->paragraph,EXR_NODE_BREAK,"br",NULL)==SIZE_MAX) return 0;
  } else c->paragraph=SIZE_MAX;
  return 1;
}
static int style_control(rtf_context *c,rtf_state *s,const char *word,long value,int has) {
  int key=-1;
  if(!strcmp(word,"b")) key=BOLD;
  else if(!strcmp(word,"i")) key=ITALIC;
  else if(!strcmp(word,"ul") || !strcmp(word,"ulnone")) key=UNDERLINE;
  else if(!strcmp(word,"strike")) key=STRIKE;
  if(key>=0) s->properties[key]=strcmp(word,"ulnone") && (!has || value!=0);
  else if(!strcmp(word,"fs")) { if(!has || value<1 || value>32767) return 0; s->properties[SIZE]=(int)value; }
  else if(!strcmp(word,"cf") || !strcmp(word,"highlight")) {
    if(!has || value<0 || value>=4096) return 0;
    s->properties[!strcmp(word,"cf") ? COLOR : BACKGROUND]=(int)value;
  } else if(!strcmp(word,"ql")) s->properties[ALIGN]=0;
  else if(!strcmp(word,"qr")) s->properties[ALIGN]=1;
  else if(!strcmp(word,"qc")) s->properties[ALIGN]=2;
  else if(!strcmp(word,"qj")) s->properties[ALIGN]=3;
  else if(!strcmp(word,"ltrpar")) s->properties[DIRECTION]=1;
  else if(!strcmp(word,"rtlpar")) s->properties[DIRECTION]=2;
  else if(!strcmp(word,"plain")) memset(s->properties,0,ALIGN*sizeof(*s->properties));
  else if(!strcmp(word,"pard")) memset(s->properties+ALIGN,0,(RTF_PROPERTIES-ALIGN)*sizeof(*s->properties));
  else {
    if(!strcmp(word,"li")) key=LEFT;
    else if(!strcmp(word,"ri")) key=RIGHT;
    else if(!strcmp(word,"fi")) key=INDENT;
    else if(!strcmp(word,"sb")) key=BEFORE;
    else if(!strcmp(word,"sa")) key=AFTER;
    else if(!strcmp(word,"sl")) key=LEADING;
    else if(!strcmp(word,"slmult")) key=MULTIPLE;
    if(key>=0) { if(!has || value < -10000000 || value>10000000) return 0; s->properties[key]=(int)value; }
  }
  (void)c; return 1;
}
exr_status exr_rtf(exr_document *d, const void *data, size_t n, exr_error *e) {
  const unsigned char *s = data;
  rtf_state states[256] = {{0}};
  rtf_context context={0};
  size_t depth = 0, i = 0;
  int fallback = 0;
  uint32_t high = 0;

  exr_status result = EXR_FORMAT;
  if (n < 5 || memcmp(s, "{\\rtf", 5))
    return exr_fail(e, EXR_FORMAT, "Invalid RTF header");
  context.doc=d; context.error=e; context.paragraph=SIZE_MAX; states[0].uc=1;
  if(exr_model_node(d,SIZE_MAX,SIZE_MAX,EXR_NODE_DOCUMENT,NULL,NULL,0)==SIZE_MAX) return EXR_LIMIT;
  {
    size_t chapter=make(&context,0,EXR_NODE_CHAPTER,NULL,NULL),html,head,title;
    if(chapter==SIZE_MAX) return EXR_LIMIT;
    d->chapters=calloc(1,sizeof(*d->chapters)); if(!d->chapters) return EXR_MEMORY;
    d->chapter_count=d->chapter_capacity=1; d->chapters[0]=(exr_chapter){"main","book.xhtml",chapter,SIZE_MAX,1,1};
    html=make(&context,chapter,EXR_NODE_ELEMENT,"html",NULL); if(html==SIZE_MAX) return EXR_LIMIT;
    head=make(&context,html,EXR_NODE_ELEMENT,"head",NULL); if(head==SIZE_MAX) return EXR_LIMIT;
    title=make(&context,head,EXR_NODE_ELEMENT,"title",NULL); if(title==SIZE_MAX || make(&context,title,EXR_NODE_TEXT,NULL,"Untitled")==SIZE_MAX) return EXR_LIMIT;
    context.body=make(&context,html,EXR_NODE_ELEMENT,"body",NULL); if(context.body==SIZE_MAX) return EXR_LIMIT;
  }
  while (i < n) {
    unsigned c = s[i++];
    if (c == '{') {
      fallback = 0; /* Group delimiters terminate the Unicode fallback sequence. */
      if(!run_flush(&context)) goto done;
      if (depth + 1 >= 256)
        goto done;
      states[depth + 1] = states[depth];
      depth++;
      continue;
    }
    if (c == '}') {
      fallback = 0;
      if(!run_flush(&context)) goto done;
      if (!depth)
        goto done;
      depth--;
      continue;
    }
    if (c == '\\') {
      char word[40] = {0};
      size_t k = 0;
      long value = 0;
      int negative = 0, has = 0;
      if (i >= n)
        goto done;
      c = s[i++];
      if (!isalpha(c) && c != '\'') {
        if (fallback) {
          fallback--;
          continue;
        }
        if (c == '*')
          states[depth].skip = 1;
        else if ((c == '\\' || c == '{' || c == '}') && !states[depth].skip &&
                 !literal(&context,&states[depth],c))
          goto done;
        continue;
      }
      if (c == '\'') {
        unsigned a, b;
        if (n - i < 2 || !isxdigit(s[i]) || !isxdigit(s[i + 1]))
          goto done;
        a = (unsigned)(isdigit(s[i]) ? s[i] - '0' : tolower(s[i]) - 'a' + 10);
        b = (unsigned)(isdigit(s[i + 1]) ? s[i + 1] - '0' : tolower(s[i + 1]) - 'a' + 10);
        c = a * 16 + b;
        i += 2;
        if (fallback) {
          fallback--;
          continue;
        }
        if (!states[depth].skip && !literal(&context,&states[depth],exr_windows1252((unsigned char)c)))
          goto done;
        continue;
      }
      word[k++] = (char)c;
      while (i < n && isalpha(s[i])) {
        if (k < 39)
          word[k++] = (char)s[i];
        i++;
      }
      if (i < n && s[i] == '-') {
        negative = 1;
        i++;
      }
      while (i < n && isdigit(s[i])) {
        has = 1;
        if (value > 100000000)
          goto done;
        value = value * 10 + s[i++] - '0';
      }
      if (negative)
        value = -value;
      if (i < n && s[i] == ' ')
        i++;
      if (!strcmp(word, "bin")) {
        if (!has || value < 0 || (size_t)value > n - i)
          goto done;
        i += (size_t)value;
        if (fallback)
          fallback--;
        continue;
      }
      /* A whole control word counts as one fallback character, without executing it. */
      if (fallback) {
        fallback--;
        continue;
      }
      if(!states[depth].skip && !strcmp(word,"colortbl")) {
        states[depth].destination=1; context.color_count=0; context.red=context.green=context.blue=context.components=0; continue;
      }
      if(!states[depth].skip && states[depth].destination==1) {
        if(!strcmp(word,"red") || !strcmp(word,"green") || !strcmp(word,"blue")) {
          if(!has || value<0 || value>255) goto done;
          if(!strcmp(word,"red")) context.red=(unsigned)value;
          else if(!strcmp(word,"green")) context.green=(unsigned)value;
          else context.blue=(unsigned)value;
          context.components=1;
        }
        continue;
      }
      if (!strcmp(word, "fonttbl") || !strcmp(word, "stylesheet") ||
          !strcmp(word, "info") || !strcmp(word, "pict") || !strcmp(word, "object") ||
          !strcmp(word, "header") || !strcmp(word, "footer")) {
        states[depth].skip = 1;
        continue;
      }
      if (states[depth].skip)
        continue;
      if (!strcmp(word, "ansicpg") && value != 1252)
        goto done;
      if (!strcmp(word, "uc")) {
        if (!has || value < 0 || value > 16)
          goto done;
        states[depth].uc = (int)value;
      } else if (!strcmp(word, "u")) {
        uint32_t cp;
        if (!has || value < -32768 || value > 65535)
          goto done;
        cp = (uint16_t)value;
        if (cp >= 0xd800 && cp <= 0xdbff) {
          if (high)
            goto done;
          high = cp;
        } else {
          if (cp >= 0xdc00 && cp <= 0xdfff) {
            if (!high)
              goto done;
            cp = 0x10000 + ((high - 0xd800) << 10) + (cp - 0xdc00);
            high = 0;
          } else if (high)
            goto done;
          if (!cp || !literal(&context,&states[depth],cp))
            goto done;
        }
        fallback = states[depth].uc;
      } else if (!strcmp(word, "par") || !strcmp(word, "line")) {
        if (!line_break(&context,&states[depth],!strcmp(word,"line")))
          goto done;
      } else if (!strcmp(word, "tab")) {
        if (!literal(&context,&states[depth],' '))
          goto done;
      } else if(!style_control(&context,&states[depth],word,value,has)) goto done;
      continue;
    }
    if (c == '\r' || c == '\n' || states[depth].skip)
      continue;
    if (fallback) {
      fallback--;
      continue;
    }
    if (high || !c || !literal(&context,&states[depth],exr_windows1252((unsigned char)c)))
      goto done;
  }
  if (depth || high || !run_flush(&context))
    goto done;
  result = EXR_OK;
done:
  free(context.run.data);
  if(result==EXR_OK) return EXR_OK;
  result=context.status!=EXR_OK ? context.status : EXR_FORMAT;
  return exr_fail(e,result,"Invalid or unsupported RTF stream");
}
