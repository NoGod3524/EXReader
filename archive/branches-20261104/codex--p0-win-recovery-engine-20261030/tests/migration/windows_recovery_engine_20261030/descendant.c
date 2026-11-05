/* SPDX-License-Identifier: MIT */
#include <windows.h>
#include <wchar.h>
int wmain(int argc,wchar_t **argv){
 WCHAR self[4096],command[4200];STARTUPINFOW s={sizeof(s)};PROCESS_INFORMATION p={0};
 
 if(argc==2&&!wcscmp(argv[1],L"child")){Sleep(30000);return 0;}
 if(!GetModuleFileNameW(NULL,self,4096))return 2;
 if(swprintf(command,4200,L"\"%ls\" child",self)<0)return 3;
 if(!CreateProcessW(self,command,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,NULL,&s,&p))return 4;
 CloseHandle(p.hThread);CloseHandle(p.hProcess);return 0;
}
