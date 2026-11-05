// SPDX-License-Identifier: MIT
// Synthetic controls only. Never loaded into or linked with the product.
#include <windows.h>
#include <d3d11.h>
#include <cstdio>
#include <cwchar>
static bool use_gdi;
static unsigned ticks,paints;
static unsigned long pixels[64*64];
static ID3D11Device *device;
static ID3D11DeviceContext *context;
static IDXGISwapChain *chain;
static ID3D11RenderTargetView *target;
static long long qpc(){LARGE_INTEGER value;QueryPerformanceCounter(&value);return value.QuadPart;}
static void record(const char *kind,long long start,HRESULT result){
 std::printf("{\"kind\":\"%s\",\"pid\":%lu,\"tick\":%u,\"start_qpc\":%lld,\"end_qpc\":%lld,\"result\":%ld}\n",
             kind,GetCurrentProcessId(),ticks,start,qpc(),static_cast<long>(result));
 std::fflush(stdout);
}
static LRESULT CALLBACK window_proc(HWND window,UINT message,WPARAM wparam,LPARAM lparam){
 switch(message){
  case WM_TIMER:{
   ++ticks;
   if(ticks>40){DestroyWindow(window);return 0;}
   if(use_gdi)InvalidateRect(window,nullptr,FALSE);
   else{
    float color[4]={static_cast<float>(ticks%4)/4.0f,0.25f,0.5f,1.0f};
    long long start=qpc();context->ClearRenderTargetView(target,color);
    HRESULT hr=chain->Present(1,0);record("dxgi_present",start,hr);
    if(FAILED(hr)){DestroyWindow(window);return 0;}
   }
   return 0;
  }
  case WM_PAINT:{
   PAINTSTRUCT paint;long long start=qpc();HDC dc=BeginPaint(window,&paint);
   if(use_gdi){
    RECT area;GetClientRect(window,&area);
    FillRect(dc,&area,static_cast<HBRUSH>(GetStockObject(WHITE_BRUSH)));
    for(unsigned i=0;i<64*64;i++)pixels[i]=0x00336600u+(ticks%64u)*4u;
    BITMAPINFO info={};info.bmiHeader.biSize=static_cast<DWORD>(sizeof(BITMAPINFOHEADER));
    info.bmiHeader.biWidth=64;info.bmiHeader.biHeight=-64;info.bmiHeader.biPlanes=1;
    info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
    SetStretchBltMode(dc,HALFTONE);SetBrushOrgEx(dc,0,0,nullptr);
    int rows=StretchDIBits(dc,0,0,area.right,area.bottom,0,0,64,64,pixels,&info,DIB_RGB_COLORS,SRCCOPY);
    EndPaint(window,&paint);++paints;record("gdi_paint",start,rows>0?S_OK:E_FAIL);
   }else EndPaint(window,&paint);
   return 0;
  }
  case WM_DESTROY:KillTimer(window,1);PostQuitMessage(0);return 0;
  default:return DefWindowProcW(window,message,wparam,lparam);
 }
}
int wmain(int argc,wchar_t **argv){
 if(argc!=3 || (std::wcscmp(argv[1],L"gdi") && std::wcscmp(argv[1],L"dxgi")))return 2;
 use_gdi=std::wcscmp(argv[1],L"gdi")==0;
 HANDLE ready=OpenEventW(SYNCHRONIZE,FALSE,argv[2]);if(!ready)return 3;
 DWORD wait=WaitForSingleObject(ready,15000);CloseHandle(ready);if(wait!=WAIT_OBJECT_0)return 4;
 LARGE_INTEGER frequency;QueryPerformanceFrequency(&frequency);
 std::printf("{\"kind\":\"start\",\"pid\":%lu,\"qpc_frequency\":%lld,\"mode\":\"%s\"}\n",
             GetCurrentProcessId(),frequency.QuadPart,use_gdi?"gdi":"dxgi");std::fflush(stdout);
 WNDCLASSW klass={};klass.lpfnWndProc=window_proc;klass.hInstance=GetModuleHandleW(nullptr);
 klass.lpszClassName=L"F08FrameControl";if(!RegisterClassW(&klass))return 5;
 HWND window=CreateWindowExW(0,klass.lpszClassName,L"F08 synthetic frame control",WS_OVERLAPPEDWINDOW,
                             40,40,640,480,nullptr,nullptr,klass.hInstance,nullptr);
 if(!window)return 6;
 if(!use_gdi){
  DXGI_SWAP_CHAIN_DESC desc={};desc.BufferCount=2;desc.BufferDesc.Width=640;desc.BufferDesc.Height=480;
  desc.BufferDesc.Format=DXGI_FORMAT_R8G8B8A8_UNORM;desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
  desc.OutputWindow=window;desc.SampleDesc.Count=1;desc.Windowed=TRUE;desc.SwapEffect=DXGI_SWAP_EFFECT_DISCARD;
  D3D_FEATURE_LEVEL level;
  HRESULT hr=D3D11CreateDeviceAndSwapChain(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,nullptr,0,
                   D3D11_SDK_VERSION,&desc,&chain,&device,&level,&context);
  if(FAILED(hr)){record("dxgi_init_error",qpc(),hr);DestroyWindow(window);return 7;}
  ID3D11Texture2D *buffer=nullptr;hr=chain->GetBuffer(0,__uuidof(ID3D11Texture2D),reinterpret_cast<void**>(&buffer));
  if(SUCCEEDED(hr)){hr=device->CreateRenderTargetView(buffer,nullptr,&target);buffer->Release();}
  if(FAILED(hr)){record("dxgi_target_error",qpc(),hr);DestroyWindow(window);return 8;}
 }
 ShowWindow(window,SW_SHOW);UpdateWindow(window);
 if(!SetTimer(window,1,100,nullptr)){DestroyWindow(window);return 9;}
 MSG message;
 while(GetMessageW(&message,nullptr,0,0)>0){TranslateMessage(&message);DispatchMessageW(&message);}
 if(target)target->Release();if(chain)chain->Release();if(context)context->Release();if(device)device->Release();
 std::printf("{\"kind\":\"stop\",\"pid\":%lu,\"ticks\":%u,\"paints\":%u}\n",GetCurrentProcessId(),ticks,paints);
 return ticks==41 && (!use_gdi || paints>=35)?0:10;
}
