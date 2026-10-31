/* SPDX-License-Identifier: MIT
 * Passive native desktop pixels. No product modification or simulated presents.
 * LastPresentTime is a desktop-update QPC, not physical scanout or paint identity.
 */
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wrl/client.h>
#include <array>
#include <vector>
#include <string>
#include <filesystem>
#include <cstdio>
#include <cstring>
#include <stdexcept>
using Microsoft::WRL::ComPtr;
namespace fs=std::filesystem;
static LONGLONG tick(){LARGE_INTEGER n{};QueryPerformanceCounter(&n);return n.QuadPart;}
static void check(HRESULT hr,const char *where){if(FAILED(hr)){std::printf("{\"kind\":\"error\",\"stage\":\"%s\",\"hresult\":\"0x%08lX\"}\n",where,(unsigned long)hr);throw std::runtime_error(where);}}
struct Region {
 HWND hwnd{};int id{};RECT rect{};DWORD pid{};bool visible{},unoccluded{},bounds{},stable{};
};
static Region region(HWND parent,int id,DWORD pid,const RECT &screen){
 Region r{};r.hwnd=GetDlgItem(parent,id);r.id=id;
 GetWindowThreadProcessId(r.hwnd,&r.pid);RECT client{};POINT origin{};
 if(!r.hwnd || r.pid!=pid || !GetClientRect(r.hwnd,&client) || !ClientToScreen(r.hwnd,&origin))return r;
 r.rect={origin.x,origin.y,origin.x+client.right,origin.y+client.bottom};
 r.visible=IsWindowVisible(r.hwnd)!=FALSE;
 r.bounds=client.right>4 && client.bottom>4 && r.rect.left>=screen.left && r.rect.top>=screen.top &&
  r.rect.right<=screen.right && r.rect.bottom<=screen.bottom;
 r.unoccluded=r.visible && r.bounds;
 if(r.unoccluded){
  POINT points[]={{r.rect.left+2,r.rect.top+2},{r.rect.right-3,r.rect.top+2},
   {r.rect.left+2,r.rect.bottom-3},{r.rect.right-3,r.rect.bottom-3},
   {(r.rect.left+r.rect.right)/2,(r.rect.top+r.rect.bottom)/2}};
  for(auto p:points)if(WindowFromPoint(p)!=r.hwnd)r.unoccluded=false;
 }
 return r;
}
static bool same(const Region &a,const Region &b){
 return a.hwnd==b.hwnd && a.pid==b.pid && a.visible==b.visible && a.unoccluded==b.unoccluded &&
  a.bounds==b.bounds && EqualRect(&a.rect,&b.rect);
}
struct Slot{
 ComPtr<ID3D11Texture2D> texture;DXGI_OUTDUPL_FRAME_INFO info{};std::array<Region,2> regions{};
 LONGLONG start{},acquired{},geometry{};unsigned index{};bool used{};
};
struct Image{std::vector<unsigned char> pixels;LONG width{},height{};unsigned index{};};
static void bitmap(const fs::path &path,const std::vector<unsigned char> &pixels,LONG width,LONG height){
 BITMAPFILEHEADER file{};file.bfType=0x4d42;file.bfOffBits=sizeof(file)+sizeof(BITMAPINFOHEADER);
 file.bfSize=file.bfOffBits+(DWORD)pixels.size();BITMAPINFOHEADER info{};
 info.biSize=sizeof(info);info.biWidth=width;info.biHeight=-height;info.biPlanes=1;info.biBitCount=32;info.biSizeImage=(DWORD)pixels.size();
 FILE *stream=nullptr;if(_wfopen_s(&stream,path.c_str(),L"wb") || !stream)throw std::runtime_error("open bitmap");
 bool ok=std::fwrite(&file,sizeof(file),1,stream)==1 && std::fwrite(&info,sizeof(info),1,stream)==1 &&
  std::fwrite(pixels.data(),pixels.size(),1,stream)==1;
 if(std::fclose(stream) || !ok)throw std::runtime_error("write bitmap");
}
static bool observe(HWND parent,DWORD pid,IDXGIAdapter1 *adapter,IDXGIOutput *output,const DXGI_OUTPUT_DESC &description,const fs::path &stop,const fs::path &folder){
 ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;D3D_FEATURE_LEVEL level{};
 check(D3D11CreateDevice(adapter,D3D_DRIVER_TYPE_UNKNOWN,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,nullptr,0,
  D3D11_SDK_VERSION,device.GetAddressOf(),&level,context.GetAddressOf()),"D3D11CreateDevice");
 ComPtr<IDXGIOutput1> output1;check(output->QueryInterface(IID_PPV_ARGS(output1.GetAddressOf())),"IDXGIOutput1");
 ComPtr<IDXGIOutputDuplication> duplication;check(output1->DuplicateOutput(device.Get(),duplication.GetAddressOf()),"DuplicateOutput");
 DXGI_OUTDUPL_DESC desc{};duplication->GetDesc(&desc);
 if(desc.ModeDesc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM || (desc.Rotation!=DXGI_MODE_ROTATION_IDENTITY && desc.Rotation!=DXGI_MODE_ROTATION_UNSPECIFIED))
  throw std::runtime_error("unsupported native desktop format or rotation");
 std::printf("{\"kind\":\"ready\",\"qpc\":%lld,\"width\":%u,\"height\":%u,\"format\":%u,\"rotation\":%u,\"ring_slots\":8}\n",
  tick(),desc.ModeDesc.Width,desc.ModeDesc.Height,desc.ModeDesc.Format,desc.Rotation);std::fflush(stdout);
 D3D11_TEXTURE2D_DESC td{};td.Width=desc.ModeDesc.Width;td.Height=desc.ModeDesc.Height;td.MipLevels=1;td.ArraySize=1;
 td.Format=desc.ModeDesc.Format;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_STAGING;td.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
 std::array<Slot,8> slots{};for(auto &slot:slots)check(device->CreateTexture2D(&td,nullptr,slot.texture.GetAddressOf()),"staging");
 std::array<Image,2> last{};unsigned head=0,tail=0,pending=0,frames=0,pointer_only=0,extra=0,backpressure=0;
 auto drain=[&](bool block){
  if(!pending)return false;auto &slot=slots[tail];D3D11_MAPPED_SUBRESOURCE map{};
  HRESULT hr=context->Map(slot.texture.Get(),0,D3D11_MAP_READ,block?0:D3D11_MAP_FLAG_DO_NOT_WAIT,&map);
  if(hr==DXGI_ERROR_WAS_STILL_DRAWING)return false;check(hr,"Map");
  std::printf("{\"kind\":\"frame\",\"index\":%u,\"start_qpc\":%lld,\"acquired_qpc\":%lld,\"last_present_qpc\":%lld,"
   "\"last_mouse_qpc\":%lld,\"accumulated_frames\":%u,\"rects_coalesced\":%s,\"protected_content\":%s,\"geometry_qpc\":%lld,\"regions\":[",
   slot.index,slot.start,slot.acquired,slot.info.LastPresentTime.QuadPart,slot.info.LastMouseUpdateTime.QuadPart,
   slot.info.AccumulatedFrames,slot.info.RectsCoalesced?"true":"false",slot.info.ProtectedContentMaskedOut?"true":"false",slot.geometry);
  for(size_t j=0;j<2;j++){
   const auto &r=slot.regions[j];auto &previous=last[j];bool valid=r.pid==pid && r.visible && r.bounds && r.unoccluded && r.stable &&
    !slot.info.ProtectedContentMaskedOut && slot.info.LastPresentTime.QuadPart>0;
   bool changed=false;std::string name;
   if(valid){
    LONG width=r.rect.right-r.rect.left,height=r.rect.bottom-r.rect.top;std::vector<unsigned char> pixels((size_t)width*height*4);
    for(LONG y=0;y<height;y++){
     auto src=(unsigned char*)map.pData+(size_t)(r.rect.top-description.DesktopCoordinates.top+y)*map.RowPitch+
      (size_t)(r.rect.left-description.DesktopCoordinates.left)*4;
     auto dst=pixels.data()+(size_t)y*width*4;std::memcpy(dst,src,(size_t)width*4);
     // Desktop alpha is not content. Retain exact BGR and make the BMP opaque.
     for(LONG x=0;x<width;x++)dst[x*4+3]=255;
    }
    changed=previous.width!=width || previous.height!=height || previous.pixels!=pixels;
    if(changed){previous.pixels=std::move(pixels);previous.width=width;previous.height=height;previous.index=slot.index;
     name=std::to_string(r.id)+"-"+std::to_string(previous.index)+".bmp";bitmap(folder/name,previous.pixels,width,height);}
    else name=std::to_string(r.id)+"-"+std::to_string(previous.index)+".bmp";
   }
   std::printf("%s{\"control_id\":%d,\"hwnd\":%llu,\"pid\":%lu,\"rect\":[%ld,%ld,%ld,%ld],"
    "\"visible\":%s,\"unoccluded\":%s,\"in_bounds\":%s,\"geometry_stable\":%s,\"valid\":%s,\"changed\":%s,\"image\":\"%s\"}",
    j?",":"",r.id,(unsigned long long)(uintptr_t)r.hwnd,r.pid,r.rect.left,r.rect.top,r.rect.right,r.rect.bottom,
    r.visible?"true":"false",r.unoccluded?"true":"false",r.bounds?"true":"false",r.stable?"true":"false",
    valid?"true":"false",changed?"true":"false",name.c_str());
  }
  context->Unmap(slot.texture.Get(),0);
  std::printf("],\"readback_finished_qpc\":%lld}\n",tick());std::fflush(stdout);
  slot.used=false;tail=(tail+1)%slots.size();pending--;return true;
 };
 ULONGLONG deadline=GetTickCount64()+600000;
 while(!fs::exists(stop) && IsWindow(parent) && GetTickCount64()<deadline){
  while(drain(false)){}
  if(pending==slots.size()){backpressure++;drain(true);}
  auto &slot=slots[head];std::array<Region,2> before={region(parent,119,pid,description.DesktopCoordinates),region(parent,123,pid,description.DesktopCoordinates)};
  ComPtr<IDXGIResource> resource;DXGI_OUTDUPL_FRAME_INFO info{};LONGLONG start=tick();
  HRESULT hr=duplication->AcquireNextFrame(5,&info,resource.GetAddressOf());LONGLONG acquired=tick();
  if(hr==DXGI_ERROR_WAIT_TIMEOUT)continue;check(hr,"AcquireNextFrame");frames++;
  if(info.AccumulatedFrames>1)extra+=info.AccumulatedFrames-1;
  if(!info.LastPresentTime.QuadPart){
   pointer_only++;std::printf("{\"kind\":\"pointer_only\",\"index\":%u,\"acquired_qpc\":%lld,\"last_mouse_qpc\":%lld,\"accumulated_frames\":%u}\n",
    frames,acquired,info.LastMouseUpdateTime.QuadPart,info.AccumulatedFrames);
   check(duplication->ReleaseFrame(),"ReleaseFrame");continue;
  }
  slot.regions={region(parent,119,pid,description.DesktopCoordinates),region(parent,123,pid,description.DesktopCoordinates)};
  for(size_t j=0;j<2;j++)slot.regions[j].stable=same(before[j],slot.regions[j]);
  slot.geometry=tick();slot.info=info;slot.start=start;slot.acquired=acquired;slot.index=frames;slot.used=true;
  ComPtr<ID3D11Texture2D> source;check(resource.As(&source),"DesktopTexture");
  context->CopyResource(slot.texture.Get(),source.Get());context->Flush();
  check(duplication->ReleaseFrame(),"ReleaseFrame");pending++;head=(head+1)%slots.size();
 }
 while(pending)drain(true);
 bool expired=GetTickCount64()>=deadline;
 std::printf("{\"kind\":\"summary\",\"qpc\":%lld,\"desktop_records\":%u,\"pointer_only\":%u,\"accumulated_extra_frames\":%u,"
  "\"ring_backpressure\":%u,\"deadline_expired\":%s,\"f08_accepted\":false}\n",tick(),frames,pointer_only,extra,backpressure,expired?"true":"false");
 return !expired && frames>0;
}
int wmain(int argc,wchar_t **argv){
 setvbuf(stdout,nullptr,_IOLBF,65536);SetProcessDPIAware();
 try{
  if(argc!=5)throw std::runtime_error("arguments: root_hwnd pid stop_file image_folder");
  HWND root=(HWND)(uintptr_t)std::stoull(argv[1]);DWORD pid=(DWORD)std::stoul(argv[2]),owner=0;
  GetWindowThreadProcessId(root,&owner);if(owner!=pid || !IsWindow(root))throw std::runtime_error("product window ownership");
  LARGE_INTEGER frequency{};QueryPerformanceFrequency(&frequency);
  std::printf("{\"kind\":\"start\",\"observer_pid\":%lu,\"product_pid\":%lu,\"root_hwnd\":%llu,\"qpc\":%lld,\"frequency\":%lld}\n",
   GetCurrentProcessId(),pid,(unsigned long long)(uintptr_t)root,tick(),frequency.QuadPart);
  fs::path folder=argv[4];fs::create_directories(folder);
  HMONITOR monitor=MonitorFromWindow(root,MONITOR_DEFAULTTONEAREST);ComPtr<IDXGIFactory1> factory;
  check(CreateDXGIFactory1(IID_PPV_ARGS(factory.GetAddressOf())),"CreateDXGIFactory1");
  for(UINT ai=0;ai<16;ai++){
   ComPtr<IDXGIAdapter1> adapter;HRESULT hr=factory->EnumAdapters1(ai,adapter.GetAddressOf());if(hr==DXGI_ERROR_NOT_FOUND)break;check(hr,"EnumAdapters1");
   DXGI_ADAPTER_DESC1 ad{};adapter->GetDesc1(&ad);
   for(UINT oi=0;oi<16;oi++){
    ComPtr<IDXGIOutput> output;hr=adapter->EnumOutputs(oi,output.GetAddressOf());if(hr==DXGI_ERROR_NOT_FOUND)break;check(hr,"EnumOutputs");
    DXGI_OUTPUT_DESC description{};output->GetDesc(&description);
    if(description.AttachedToDesktop && description.Monitor==monitor){
     std::printf("{\"kind\":\"adapter\",\"vendor\":%u,\"device\":%u,\"flags\":%u}\n",ad.VendorId,ad.DeviceId,ad.Flags);
     bool success=observe(root,pid,adapter.Get(),output.Get(),description,argv[3],folder);std::fflush(stdout);return success?0:1;
    }
   }
  }
  throw std::runtime_error("no output for product monitor");
 }catch(const std::exception &error){std::printf("{\"kind\":\"fatal\",\"message\":\"%s\",\"qpc\":%lld}\n",error.what(),tick());std::fflush(stdout);return 1;}
}
