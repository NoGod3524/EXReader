/* SPDX-License-Identifier: MIT */
#include <stdio.h>
extern int c_contract(void);
int main(void){
  int code=c_contract();
  if(code)printf("{\"contract_failure\":%d}\n",code);
  return code;
}
