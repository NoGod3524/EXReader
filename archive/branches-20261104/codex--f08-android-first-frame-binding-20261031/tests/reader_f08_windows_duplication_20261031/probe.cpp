/* SPDX-License-Identifier: MIT
 * Native desktop-frame capability control. This is never a product benchmark.
 */
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
using Microsoft::WRL::ComPtr;
static unsigned generation;
static LONGLONG paint_start,paint_end,frequency;
static LONGLONG qpc(){LARGE_INTEGER n{};QueryPerformanceCounter(&n);return n.QuadPart;}
static COLORREF color(){return RGB(generation*20u,37u,191u-generation*11u);}
static void error(const char *stage,HRESULT hr){
 std::printf("{\"kind\":\"error\",\"stage\":\"%s\",\"hresult\":\"0x%08lX\"}\n",stage,static_cast<unsigned long>(hr));
}
static LRESULT CALLBACK window_proc(HWND window,UINT message,WPARAM w,LPARAM l){
 if(message==WM_PAINT){
  paint_start=qpc();PAINTSTRUCT paint{};HDC dc=BeginPaint(window,&paint);RECT rect{};
  GetClientRect(window,&rect);HBRUSH brush=CreateSolidBrush(color());FillRect(dc,&rect,brush);DeleteObject(brush);
  EndPaint(window,&paint);paint_end=qpc();
  std::printf("{\"kind\":\"control_paint\",\"generation\":%u,\"start_qpc\":%lld,\"end_qpc\":%lld}\n",
   generation,paint_start,paint_end);return 0;
 }
 return DefWindowProcW(window,message,w,l);
}
static void pump(){MSG m{};while(PeekMessageW(&m,nullptr,0,0,PM_REMOVE)){TranslateMessage(&m);DispatchMessageW(&m);}}
static bool capture(HWND window,IDXGIAdapter1 *adapter,IDXGIOutput *output,DXGI_OUTPUT_DESC description){
 ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;D3D_FEATURE_LEVEL level{};
 HRESULT hr=D3D11CreateDevice(adapter,D3D_DRIVER_TYPE_UNKNOWN,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
  nullptr,0,D3D11_SDK_VERSION,device.GetAddressOf(),&level,context.GetAddressOf());
 if(FAILED(hr)){error("D3D11CreateDevice",hr);return false;}
 ComPtr<IDXGIOutput1> output1;hr=output->QueryInterface(IID_PPV_ARGS(output1.GetAddressOf()));
 if(FAILED(hr)){error("IDXGIOutput1",hr);return false;}
 ComPtr<IDXGIOutputDuplication> duplication;hr=output1->DuplicateOutput(device.Get(),duplication.GetAddressOf());
 if(FAILED(hr)){error("DuplicateOutput",hr);return false;}
 DXGI_OUTDUPL_DESC desc{};duplication->GetDesc(&desc);
 std::printf("{\"kind\":\"duplication\",\"width\":%u,\"height\":%u,\"format\":%u,\"rotation\":%u,\"feature_level\":%u}\n",
  desc.ModeDesc.Width,desc.ModeDesc.Height,desc.ModeDesc.Format,desc.Rotation,level);
 if(desc.ModeDesc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM ||
    (desc.Rotation!=DXGI_MODE_ROTATION_IDENTITY && desc.Rotation!=DXGI_MODE_ROTATION_UNSPECIFIED)){
  error("unsupported_format_or_rotation",E_NOTIMPL);return false;
 }
 D3D11_TEXTURE2D_DESC pixel_desc{};pixel_desc.Width=1;pixel_desc.Height=1;pixel_desc.MipLevels=1;
 pixel_desc.ArraySize=1;pixel_desc.Format=desc.ModeDesc.Format;pixel_desc.SampleDesc.Count=1;
 pixel_desc.Usage=D3D11_USAGE_STAGING;pixel_desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
 ComPtr<ID3D11Texture2D> pixel;hr=device->CreateTexture2D(&pixel_desc,nullptr,pixel.GetAddressOf());
 if(FAILED(hr)){error("pixel_staging",hr);return false;}
 POINT center{80,80};if(!ClientToScreen(window,&center)){error("control_coordinates",HRESULT_FROM_WIN32(GetLastError()));return false;}
 LONG x=center.x-description.DesktopCoordinates.left,y=center.y-description.DesktopCoordinates.top;
 if(x<0 || y<0 || static_cast<UINT>(x)>=desc.ModeDesc.Width || static_cast<UINT>(y)>=desc.ModeDesc.Height){
  error("control_outside_output",E_BOUNDS);return false;
 }
 unsigned matched_count=0,total_frames=0,accumulated_extras=0,pointer_only=0;
 for(generation=1;generation<=8;generation++){
  InvalidateRect(window,nullptr,FALSE);UpdateWindow(window);
  LONGLONG expected_paint_start=paint_start,expected_paint_end=paint_end;
  ULONGLONG deadline=GetTickCount64()+2000;bool matched=false;
  while(GetTickCount64()<deadline && !matched){
   pump();DXGI_OUTDUPL_FRAME_INFO info{};ComPtr<IDXGIResource> resource;LONGLONG start=qpc();
   hr=duplication->AcquireNextFrame(50,&info,resource.GetAddressOf());LONGLONG acquired=qpc();
   if(hr==DXGI_ERROR_WAIT_TIMEOUT)continue;
   if(FAILED(hr)){error("AcquireNextFrame",hr);return false;}
   ComPtr<ID3D11Texture2D> texture;hr=resource.As(&texture);
   unsigned char bgra[4]={0,0,0,0};bool read=false;
   if(SUCCEEDED(hr)){
    D3D11_BOX box{static_cast<UINT>(x),static_cast<UINT>(y),0,static_cast<UINT>(x+1),static_cast<UINT>(y+1),1};
    context->CopySubresourceRegion(pixel.Get(),0,0,0,0,texture.Get(),0,&box);
    D3D11_MAPPED_SUBRESOURCE map{};hr=context->Map(pixel.Get(),0,D3D11_MAP_READ,0,&map);
    if(SUCCEEDED(hr)){std::memcpy(bgra,map.pData,4);context->Unmap(pixel.Get(),0);read=true;}
   }
   HRESULT release=duplication->ReleaseFrame();LONGLONG finished=qpc();total_frames++;
   if(info.AccumulatedFrames>1)accumulated_extras+=info.AccumulatedFrames-1;
   if(info.LastPresentTime.QuadPart==0)pointer_only++;
   COLORREF expected=color();
   matched=read && info.LastPresentTime.QuadPart>=expected_paint_start && info.LastPresentTime.QuadPart<=acquired &&
     !info.ProtectedContentMaskedOut && info.AccumulatedFrames>0 &&
     bgra[0]==GetBValue(expected) && bgra[1]==GetGValue(expected) && bgra[2]==GetRValue(expected);
   std::printf("{\"kind\":\"desktop_frame\",\"requested_generation\":%u,\"start_qpc\":%lld,\"acquired_qpc\":%lld,"
    "\"finished_qpc\":%lld,\"last_present_qpc\":%lld,\"last_mouse_qpc\":%lld,\"accumulated_frames\":%u,"
    "\"rects_coalesced\":%s,\"protected_content\":%s,\"pixel_read\":%s,\"bgra\":[%u,%u,%u,%u],"
    "\"paint_start_qpc\":%lld,\"paint_end_qpc\":%lld,\"matched\":%s}\n",
    generation,start,acquired,finished,info.LastPresentTime.QuadPart,info.LastMouseUpdateTime.QuadPart,
    info.AccumulatedFrames,info.RectsCoalesced?"true":"false",info.ProtectedContentMaskedOut?"true":"false",
    read?"true":"false",bgra[0],bgra[1],bgra[2],bgra[3],expected_paint_start,expected_paint_end,matched?"true":"false");
   if(FAILED(hr)){error("read_desktop_pixel",hr);return false;}
   if(FAILED(release)){error("ReleaseFrame",release);return false;}
  }
  if(matched)matched_count++;
  else {error("native_control_content_deadline",HRESULT_FROM_WIN32(WAIT_TIMEOUT));return false;}
 }
 std::printf("{\"kind\":\"summary\",\"capability_complete\":true,\"matched_generations\":%u,\"desktop_records\":%u,"
  "\"accumulated_extra_frames\":%u,\"pointer_only_records\":%u,\"product_sampled\":false,\"f08_accepted\":false}\n",
  matched_count,total_frames,accumulated_extras,pointer_only);
 return matched_count==8;
}
int main(){
 LARGE_INTEGER f{};QueryPerformanceFrequency(&f);frequency=f.QuadPart;SetProcessDPIAware();
 std::printf("{\"kind\":\"start\",\"pid\":%lu,\"qpc_frequency\":%lld,\"scope\":\"isolated GDI capability control\"}\n",GetCurrentProcessId(),frequency);
 WNDCLASSW cls{};cls.lpfnWndProc=window_proc;cls.hInstance=GetModuleHandleW(nullptr);cls.lpszClassName=L"F08NativeDuplication";
 if(!RegisterClassW(&cls)){error("RegisterClass",HRESULT_FROM_WIN32(GetLastError()));return 1;}
 HWND window=CreateWindowExW(WS_EX_TOPMOST,cls.lpszClassName,L"F08 isolated desktop-frame control",
  WS_OVERLAPPEDWINDOW|WS_VISIBLE,40,40,320,240,nullptr,nullptr,cls.hInstance,nullptr);
 if(!window){error("CreateWindow",HRESULT_FROM_WIN32(GetLastError()));return 1;}
 pump();UpdateWindow(window);HMONITOR target=MonitorFromWindow(window,MONITOR_DEFAULTTONEAREST);
 ComPtr<IDXGIFactory1> factory;HRESULT hr=CreateDXGIFactory1(IID_PPV_ARGS(factory.GetAddressOf()));
 bool success=false,found=false;
 if(FAILED(hr))error("CreateDXGIFactory1",hr);
 else{
  for(UINT ai=0;ai<16 && !found;ai++){
   ComPtr<IDXGIAdapter1> adapter;hr=factory->EnumAdapters1(ai,adapter.GetAddressOf());if(hr==DXGI_ERROR_NOT_FOUND)break;
   if(FAILED(hr)){error("EnumAdapters1",hr);break;}
   DXGI_ADAPTER_DESC1 desc{};adapter->GetDesc1(&desc);
   std::printf("{\"kind\":\"adapter\",\"index\":%u,\"vendor\":%u,\"device\":%u,\"flags\":%u}\n",ai,desc.VendorId,desc.DeviceId,desc.Flags);
   for(UINT oi=0;oi<16;oi++){
    ComPtr<IDXGIOutput> output;hr=adapter->EnumOutputs(oi,output.GetAddressOf());if(hr==DXGI_ERROR_NOT_FOUND)break;
    if(FAILED(hr)){error("EnumOutputs",hr);break;}
    DXGI_OUTPUT_DESC d{};output->GetDesc(&d);
    std::printf("{\"kind\":\"output\",\"adapter\":%u,\"index\":%u,\"attached\":%s,\"target_monitor\":%s}\n",
     ai,oi,d.AttachedToDesktop?"true":"false",d.Monitor==target?"true":"false");
    if(d.AttachedToDesktop && d.Monitor==target){found=true;success=capture(window,adapter.Get(),output.Get(),d);break;}
   }
  }
 }
 if(!found)error("no_adapter_output_for_control_monitor",DXGI_ERROR_NOT_FOUND);
 DestroyWindow(window);std::fflush(stdout);return success?0:1;
}
