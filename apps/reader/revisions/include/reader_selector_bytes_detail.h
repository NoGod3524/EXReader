/* SPDX-License-Identifier: MIT
   Private C++ implementation shared by the optional installed candidate codecs. */
#ifndef READER_SELECTOR_BYTES_DETAIL_H
#define READER_SELECTOR_BYTES_DETAIL_H
#include <cstddef>
#include <string>
namespace reader_selector_bytes_detail {
enum class result { ok, format, limit };
inline bool utf8(const std::string &s,size_t maximum){
  size_t count=0;
  for(size_t i=0;i<s.size();){
    unsigned a=(unsigned char)s[i++],cp=a;size_t n=0;
    if(a<128){}
    else if(a>=0xc2&&a<=0xdf){cp=a&31;n=1;}
    else if(a>=0xe0&&a<=0xef){cp=a&15;n=2;}
    else if(a>=0xf0&&a<=0xf4){cp=a&7;n=3;}
    else return false;
    if(n>s.size()-i)return false;
    for(size_t k=0;k<n;k++){unsigned b=(unsigned char)s[i++];if((b&0xc0)!=0x80)return false;cp=(cp<<6)|(b&63);}
    if((n==1&&cp<128)||(n==2&&cp<2048)||(n==3&&cp<65536)||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
    if(++count>maximum)return false;
  }
  return true;
}
inline std::string encode(const char *data,size_t size){
  static const char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;out.reserve(4*((size+2)/3));
  for(size_t i=0;i<size;i+=3){
    unsigned a=(unsigned char)data[i],b=i+1<size?(unsigned char)data[i+1]:0,c=i+2<size?(unsigned char)data[i+2]:0;
    out+=alphabet[a>>2];out+=alphabet[((a&3)<<4)|(b>>4)];out+=i+1<size?alphabet[((b&15)<<2)|(c>>6)]:'=';out+=i+2<size?alphabet[c&63]:'=';
  }
  return out;
}
inline int digit(unsigned char c){
  if(c>='A'&&c<='Z')return c-'A';
  if(c>='a'&&c<='z')return c-'a'+26;
  if(c>='0'&&c<='9')return c-'0'+52;
  return c=='+'?62:c=='/'?63:-1;
}
inline result decode(const std::string &encoded,size_t size,size_t limit,size_t scalars,std::string &out){
  if(size>limit)return result::limit;
  if(encoded.size()!=4*((size+2)/3))return result::format;
  out.clear();out.reserve(size);
  for(size_t i=0;i<encoded.size();i+=4){
    int a=digit((unsigned char)encoded[i]),b=digit((unsigned char)encoded[i+1]);
    int c=encoded[i+2]=='='?0:digit((unsigned char)encoded[i+2]),d=encoded[i+3]=='='?0:digit((unsigned char)encoded[i+3]);
    if(a<0||b<0||c<0||d<0)return result::format;
    out+=(char)((a<<2)|(b>>4));if(out.size()<size)out+=(char)((b<<4)|(c>>2));if(out.size()<size)out+=(char)((c<<6)|d);
  }
  /* Re-encoding enforces padding positions and zero pad bits, including '='. */
  if(out.size()!=size||encode(out.data(),out.size())!=encoded||!utf8(out,scalars))return result::format;
  return result::ok;
}
}
#endif
