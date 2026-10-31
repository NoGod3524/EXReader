/* SPDX-License-Identifier: MIT
 * Passive capture of one product HWND. The native timestamp describes compositor
 * rendering; it does not establish physical scanout or a complete frame census.
 */
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <windows.graphics.capture.interop.h>
#include <windows.graphics.directx.direct3d11.interop.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Graphics.Capture.h>
#include <winrt/Windows.Graphics.DirectX.h>
#include <winrt/Windows.Graphics.DirectX.Direct3D11.h>
#include <atomic>
#include <filesystem>
#include <mutex>
#include <vector>
#include <cstdio>
using namespace winrt;
using namespace Windows::Graphics::Capture;
using namespace Windows::Graphics::DirectX;
using namespace Windows::Graphics::DirectX::Direct3D11;
namespace fs=std::filesystem;
static long long tick(){LARGE_INTEGER n{};QueryPerformanceCounter(&n);return n.QuadPart;}
static void bitmap(const fs::path&p,const std::vector<unsigned char>&bytes,LONG w,LONG h){
 BITMAPFILEHEADER f{};BITMAPINFOHEADER b{};f.bfType=0x4d42;f.bfOffBits=sizeof(f)+sizeof(b);f.bfSize=f.bfOffBits+(DWORD)bytes.size();
 b.biSize=sizeof(b);b.biWidth=w;b.biHeight=-h;b.biPlanes=1;b.biBitCount=32;b.biSizeImage=(DWORD)bytes.size();
 FILE*s=nullptr;if(_wfopen_s(&s,p.c_str(),L"wb")||!s)throw hresult_error(E_FAIL,L"open bitmap");
 bool ok=fwrite(&f,sizeof(f),1,s)==1&&fwrite(&b,sizeof(b),1,s)==1&&fwrite(bytes.data(),bytes.size(),1,s)==1;
 if(fclose(s)||!ok)throw hresult_error(E_FAIL,L"write bitmap");
}
int wmain(int argc,wchar_t**argv){
 setvbuf(stdout,nullptr,_IOLBF,65536);SetProcessDPIAware();
 try{
  if(argc!=5)throw hresult_error(E_INVALIDARG,L"root_hwnd pid stop_file image_folder");
  HWND root=(HWND)(uintptr_t)std::stoull(argv[1]);DWORD pid=(DWORD)std::stoul(argv[2]),owner=0,affinity=0;
  GetWindowThreadProcessId(root,&owner);
  if(!IsWindow(root)||owner!=pid)throw hresult_error(E_ACCESSDENIED,L"window ownership");
  bool affinity_known=GetWindowDisplayAffinity(root,&affinity)!=FALSE;
  if(affinity_known&&affinity!=WDA_NONE)throw hresult_error(E_ACCESSDENIED,L"capture protection");
  init_apartment(apartment_type::multi_threaded);
  if(!GraphicsCaptureSession::IsSupported())throw hresult_error(E_NOTIMPL,L"Windows Graphics Capture unsupported");
  LARGE_INTEGER frequency{};QueryPerformanceFrequency(&frequency);
  std::printf("{\"kind\":\"start\",\"observer_pid\":%lu,\"product_pid\":%lu,\"root_hwnd\":%llu,\"qpc\":%lld,\"frequency\":%lld,\"api\":\"Windows.Graphics.Capture\",\"affinity_known\":%s,\"display_affinity\":%lu}\n",
   GetCurrentProcessId(),pid,(unsigned long long)(uintptr_t)root,tick(),frequency.QuadPart,affinity_known?"true":"false",affinity);
  auto factory=get_activation_factory<GraphicsCaptureItem,IGraphicsCaptureItemInterop>();
  GraphicsCaptureItem item{nullptr};check_hresult(factory->CreateForWindow(root,guid_of<GraphicsCaptureItem>(),put_abi(item)));
  com_ptr<ID3D11Device> device;com_ptr<ID3D11DeviceContext> context;D3D_FEATURE_LEVEL level{};
  check_hresult(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
   nullptr,0,D3D11_SDK_VERSION,device.put(),&level,context.put()));
  auto dxgi=device.as<IDXGIDevice>();com_ptr<IDXGIAdapter> adapter;check_hresult(dxgi->GetAdapter(adapter.put()));
  auto adapter1=adapter.as<IDXGIAdapter1>();DXGI_ADAPTER_DESC1 ad{};check_hresult(adapter1->GetDesc1(&ad));
  if(ad.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)throw hresult_error(E_FAIL,L"software GPU");
  std::printf("{\"kind\":\"adapter\",\"vendor\":%u,\"device\":%u,\"flags\":%u}\n",ad.VendorId,ad.DeviceId,ad.Flags);
  com_ptr<IInspectable> inspectable;check_hresult(CreateDirect3D11DeviceFromDXGIDevice(dxgi.get(),inspectable.put()));
  auto native=inspectable.as<IDirect3DDevice>();auto size=item.Size();
  if(size.Width<=0||size.Height<=0||size.Width>4096||size.Height>4096)throw hresult_error(E_FAIL,L"window dimensions");
  auto pool=Direct3D11CaptureFramePool::CreateFreeThreaded(native,DirectXPixelFormat::B8G8R8A8UIntNormalized,8,size);
  auto session=pool.CreateCaptureSession(item);session.IsCursorCaptureEnabled(false);
  fs::path folder=argv[4],stop=argv[3];fs::create_directories(folder);
  std::mutex lock;std::atomic<bool> failed{false},closed{false};unsigned frames=0,changed_images=0,last=0;unsigned long long saved_bytes=0;
  std::vector<unsigned char> previous;com_ptr<ID3D11Texture2D> staging;D3D11_TEXTURE2D_DESC staging_desc{};
  auto closed_token=item.Closed([&](auto const&,auto const&){closed=true;});
  auto token=pool.FrameArrived([&](auto const&sender,auto const&){
   std::lock_guard<std::mutex> guard(lock);if(failed)return;
   try{
    while(auto frame=sender.TryGetNextFrame()){
     auto begin=tick();auto content=frame.ContentSize();auto relative=frame.SystemRelativeTime().count();
     DWORD current_owner=0,current_affinity=0;GetWindowThreadProcessId(root,&current_owner);
     if(current_owner!=pid||(GetWindowDisplayAffinity(root,&current_affinity)&&current_affinity!=WDA_NONE))
      throw hresult_error(E_ACCESSDENIED,L"window identity or protection changed");
     if(content.Width!=size.Width||content.Height!=size.Height)throw hresult_error(E_FAIL,L"capture resized");
     auto access=frame.Surface().template as<IDirect3DDxgiInterfaceAccess>();
     com_ptr<ID3D11Texture2D> texture;check_hresult(access->GetInterface(__uuidof(ID3D11Texture2D),texture.put_void()));
     D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
     if(!staging){staging_desc=desc;staging_desc.BindFlags=0;staging_desc.MiscFlags=0;staging_desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;staging_desc.Usage=D3D11_USAGE_STAGING;
      check_hresult(device->CreateTexture2D(&staging_desc,nullptr,staging.put()));}
     if(desc.Width!=staging_desc.Width||desc.Height!=staging_desc.Height||desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM)
      throw hresult_error(E_FAIL,L"texture format or dimensions changed");
     auto copy=tick();context->CopyResource(staging.get(),texture.get());frame.Close();
     D3D11_MAPPED_SUBRESOURCE mapped{};auto map_begin=tick();check_hresult(context->Map(staging.get(),0,D3D11_MAP_READ,0,&mapped));auto map_end=tick();
     std::vector<unsigned char> bytes((size_t)size.Width*size.Height*4);
     for(LONG y=0;y<size.Height;y++){
      auto src=(unsigned char*)mapped.pData+(size_t)y*mapped.RowPitch;auto dst=bytes.data()+(size_t)y*size.Width*4;
      memcpy(dst,src,(size_t)size.Width*4);for(LONG x=0;x<size.Width;x++)dst[x*4+3]=255;
     }
     context->Unmap(staging.get(),0);frames++;bool changed=previous!=bytes;
     if(changed){
      if(saved_bytes+bytes.size()>(1ull<<30))throw hresult_error(E_FAIL,L"image byte cap");
      last=frames;previous=std::move(bytes);saved_bytes+=previous.size();changed_images++;
      bitmap(folder/(std::to_string(last)+".bmp"),previous,size.Width,size.Height);
     }
     std::printf("{\"kind\":\"frame\",\"index\":%u,\"system_relative_100ns\":%lld,\"callback_qpc\":%lld,\"copy_qpc\":%lld,\"map_start_qpc\":%lld,\"map_end_qpc\":%lld,\"readback_finished_qpc\":%lld,\"width\":%d,\"height\":%d,\"changed\":%s,\"image\":\"%u.bmp\"}\n",
      frames,(long long)relative,begin,copy,map_begin,map_end,tick(),size.Width,size.Height,changed?"true":"false",last);std::fflush(stdout);
    }
   }catch(hresult_error const&e){std::printf("{\"kind\":\"callback_error\",\"hresult\":\"0x%08lX\",\"qpc\":%lld}\n",(unsigned long)e.code(),tick());std::fflush(stdout);failed=true;}
   catch(...){std::printf("{\"kind\":\"callback_error\",\"qpc\":%lld}\n",tick());std::fflush(stdout);failed=true;}
  });
  session.StartCapture();
  std::printf("{\"kind\":\"ready\",\"qpc\":%lld,\"width\":%d,\"height\":%d,\"frame_pool_buffers\":8,\"capture_scope\":\"owned_window\",\"cursor_capture\":false}\n",tick(),size.Width,size.Height);std::fflush(stdout);
  auto deadline=GetTickCount64()+120000;
  while(!fs::exists(stop)&&!failed&&!closed&&IsWindow(root)&&GetTickCount64()<deadline)Sleep(5);
  session.Close();pool.FrameArrived(token);pool.Close();item.Closed(closed_token);
  std::lock_guard<std::mutex> guard(lock);bool expired=GetTickCount64()>=deadline;
  std::printf("{\"kind\":\"summary\",\"qpc\":%lld,\"frames\":%u,\"changed_images\":%u,\"saved_pixel_bytes\":%llu,\"deadline_expired\":%s,\"failed\":%s,\"target_closed\":%s,\"frame_census_complete\":false,\"physical_scanout_proven\":false,\"f08_accepted\":false}\n",
   tick(),frames,changed_images,saved_bytes,expired?"true":"false",failed?"true":"false",closed?"true":"false");
  return !failed&&!expired&&frames>0?0:1;
 }catch(hresult_error const&e){std::printf("{\"kind\":\"fatal\",\"hresult\":\"0x%08lX\",\"qpc\":%lld}\n",(unsigned long)e.code(),tick());return 1;}
 catch(...){std::printf("{\"kind\":\"fatal\",\"qpc\":%lld}\n",tick());return 1;}
}
