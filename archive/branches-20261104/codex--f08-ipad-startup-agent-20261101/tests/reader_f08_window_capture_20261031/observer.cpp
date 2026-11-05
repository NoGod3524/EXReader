/* SPDX-License-Identifier: MIT
 * Passive capture of one product HWND. The native timestamp describes compositor
 * rendering; it does not establish physical scanout or a complete frame census.
 */
#include <windows.h>
#include <d3d11.h>
#include <dwmapi.h>
#include <wincodec.h>
#include <array>
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
#include <memory>
#include <vector>
#include <cstdio>
#include <string>
using namespace winrt;
using namespace winrt::Windows::Graphics::Capture;
using namespace winrt::Windows::Graphics::DirectX;
using namespace winrt::Windows::Graphics::DirectX::Direct3D11;
namespace fs=std::filesystem;
static long long tick(){LARGE_INTEGER n{};QueryPerformanceCounter(&n);return n.QuadPart;}
struct Region { HWND hwnd{}; DWORD pid{}; int id{}; RECT rect{}; bool visible{}; };
static Region region(HWND root,int id){
 Region r{};r.id=id;r.hwnd=GetDlgItem(root,id);GetWindowThreadProcessId(r.hwnd,&r.pid);
 RECT c{};POINT p{};if(!r.hwnd||!GetClientRect(r.hwnd,&c)||!ClientToScreen(r.hwnd,&p))return r;
 r.rect={p.x,p.y,p.x+c.right,p.y+c.bottom};r.visible=IsWindowVisible(r.hwnd)!=FALSE;return r;
}
static bool same(const Region&a,const Region&b){
 return a.hwnd==b.hwnd&&a.pid==b.pid&&a.visible==b.visible&&EqualRect(&a.rect,&b.rect);
}
static void bitmap(const fs::path&p,const std::vector<unsigned char>&bytes,LONG w,LONG h,bool verify=false){
 com_ptr<IWICImagingFactory> factory;
 check_hresult(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,__uuidof(IWICImagingFactory),factory.put_void()));
 com_ptr<IWICStream> stream;check_hresult(factory->CreateStream(stream.put()));check_hresult(stream->InitializeFromFilename(p.c_str(),GENERIC_WRITE));
 com_ptr<IWICBitmapEncoder> encoder;check_hresult(factory->CreateEncoder(GUID_ContainerFormatPng,nullptr,encoder.put()));
 check_hresult(encoder->Initialize(stream.get(),WICBitmapEncoderNoCache));com_ptr<IWICBitmapFrameEncode> frame;
 check_hresult(encoder->CreateNewFrame(frame.put(),nullptr));check_hresult(frame->Initialize(nullptr));check_hresult(frame->SetSize(w,h));
 auto format=GUID_WICPixelFormat32bppBGRA;check_hresult(frame->SetPixelFormat(&format));
 if(!IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA))throw hresult_error(E_FAIL,L"PNG pixel format");
 check_hresult(frame->WritePixels(h,w*4,(UINT)bytes.size(),const_cast<BYTE*>(bytes.data())));
 check_hresult(frame->Commit());check_hresult(encoder->Commit());frame=nullptr;encoder=nullptr;stream=nullptr;
 if(verify){
  com_ptr<IWICBitmapDecoder> decoder;check_hresult(factory->CreateDecoderFromFilename(p.c_str(),nullptr,GENERIC_READ,WICDecodeMetadataCacheOnLoad,decoder.put()));
  com_ptr<IWICBitmapFrameDecode> decoded;check_hresult(decoder->GetFrame(0,decoded.put()));com_ptr<IWICFormatConverter> converter;
  check_hresult(factory->CreateFormatConverter(converter.put()));check_hresult(converter->Initialize(decoded.get(),GUID_WICPixelFormat32bppBGRA,WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom));
  std::vector<unsigned char> roundtrip(bytes.size());check_hresult(converter->CopyPixels(nullptr,w*4,(UINT)roundtrip.size(),roundtrip.data()));
  if(roundtrip!=bytes)throw hresult_error(E_FAIL,L"PNG roundtrip mismatch");
 }
}
static unsigned long long capture_limit(const wchar_t*arg){
 std::wstring value(arg);size_t consumed=0;auto ms=std::stoull(value,&consumed);
 if(consumed!=value.size()||ms<1||ms>5400000)throw hresult_error(E_INVALIDARG,L"capture limit 1..5400000 ms");
 return ms;
}
int wmain(int argc,wchar_t**argv){
 setvbuf(stdout,nullptr,_IOLBF,65536);SetProcessDPIAware();
 try{
  if(argc==2&&std::wstring(argv[1])==L"--check-limits"){
   if(capture_limit(L"1")!=1||capture_limit(L"120000")!=120000||capture_limit(L"5400000")!=5400000)throw hresult_error(E_FAIL,L"capture limit positive control");
   for(const auto*value:{L"0",L"5400001",L"-1",L"120000x",L""}){
    bool rejected=false;try{capture_limit(value);}catch(...){rejected=true;}
    if(!rejected)throw hresult_error(E_FAIL,L"capture limit negative control");
   }
   std::printf("{\"capture_limit_checks\":8,\"passed\":true}\n");return 0;
  }
  if(argc==3&&std::wstring(argv[1])==L"--check-png"){
   init_apartment(apartment_type::multi_threaded);
   bitmap(argv[2],{0,17,255,255,255,1,83,255,19,27,29,255,255,255,255,255},2,2,true);return 0;
  }
  if(argc!=5&&argc!=6)throw hresult_error(E_INVALIDARG,L"root_hwnd pid stop_file image_folder [capture_limit_ms]");
  auto limit_ms=argc==6?capture_limit(argv[5]):120000ull;auto frame_limit=argc==6?(limit_ms*60+999)/1000+8:7200ull;if(frame_limit<7200)frame_limit=7200;
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
  struct Gate { std::mutex lock;bool stopping{}; };auto gate=std::make_shared<Gate>();
  std::atomic<bool> failed{false},closed{false};unsigned frames=0,changed_images=0,last=0;unsigned long long saved_bytes=0,saved_pixel_bytes=0;
  std::vector<unsigned char> previous;com_ptr<ID3D11Texture2D> staging;D3D11_TEXTURE2D_DESC staging_desc{};
  auto closed_token=item.Closed([&,gate](auto const&,auto const&){std::lock_guard<std::mutex> guard(gate->lock);if(!gate->stopping)closed=true;});
  auto token=pool.FrameArrived([&,gate](auto const&sender,auto const&){
   auto callback_entry=tick();
   std::lock_guard<std::mutex> guard(gate->lock);if(gate->stopping || failed)return;
   try{
    for(;;){
     auto acquire_begin=tick();auto frame=sender.TryGetNextFrame();auto acquire_end=tick();
     if(!frame)break;
     auto begin=acquire_end;RECT bounds{},after_bounds{};
     check_hresult(DwmGetWindowAttribute(root,DWMWA_EXTENDED_FRAME_BOUNDS,&bounds,sizeof(bounds)));
     std::array<Region,2> before={region(root,119),region(root,123)};
     auto content=frame.ContentSize();auto relative=frame.SystemRelativeTime().count();
     DWORD current_owner=0,current_affinity=0;GetWindowThreadProcessId(root,&current_owner);
     if(current_owner!=pid||(GetWindowDisplayAffinity(root,&current_affinity)&&current_affinity!=WDA_NONE))
      throw hresult_error(E_ACCESSDENIED,L"window identity or protection changed");
     if(content.Width!=size.Width||content.Height!=size.Height)throw hresult_error(E_FAIL,L"capture resized");
     auto access=frame.Surface().template as<::Windows::Graphics::DirectX::Direct3D11::IDirect3DDxgiInterfaceAccess>();
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
     context->Unmap(staging.get(),0);
     check_hresult(DwmGetWindowAttribute(root,DWMWA_EXTENDED_FRAME_BOUNDS,&after_bounds,sizeof(after_bounds)));
     std::array<Region,2> after={region(root,119),region(root,123)};
     frames++;bool changed=previous!=bytes;
     if(changed){
      if(saved_bytes>(1ull<<30)||frames>frame_limit)throw hresult_error(E_FAIL,L"image byte or frame cap");
      last=frames;previous=std::move(bytes);saved_pixel_bytes+=previous.size();changed_images++;
      auto path=folder/(std::to_string(last)+".png");bitmap(path,previous,size.Width,size.Height);saved_bytes+=fs::file_size(path);
     }
     std::printf("{\"kind\":\"frame\",\"index\":%u,\"system_relative_100ns\":%lld,\"callback_entry_qpc\":%lld,\"acquire_begin_qpc\":%lld,\"acquire_end_qpc\":%lld,\"callback_qpc\":%lld,\"copy_qpc\":%lld,\"map_start_qpc\":%lld,\"map_end_qpc\":%lld,\"readback_finished_qpc\":%lld,\"width\":%d,\"height\":%d,\"changed\":%s,\"image\":\"%u.png\",\"regions\":[",
      frames,(long long)relative,callback_entry,acquire_begin,acquire_end,begin,copy,map_begin,map_end,tick(),size.Width,size.Height,changed?"true":"false",last);
     for(unsigned j=0;j<2;j++){
      const auto&r=before[j];bool stable=same(r,after[j])&&EqualRect(&bounds,&after_bounds);
      RECT crop={r.rect.left-bounds.left,r.rect.top-bounds.top,r.rect.right-bounds.left,r.rect.bottom-bounds.top};
      bool valid=r.pid==pid&&r.visible&&stable&&!IsIconic(root)&&bounds.right-bounds.left==size.Width&&bounds.bottom-bounds.top==size.Height&&
       crop.left>=0&&crop.top>=0&&crop.right<=size.Width&&crop.bottom<=size.Height&&crop.right>crop.left&&crop.bottom>crop.top;
      std::printf("%s{\"control_id\":%d,\"hwnd\":%llu,\"pid\":%lu,\"crop\":[%ld,%ld,%ld,%ld],\"visible\":%s,\"geometry_stable\":%s,\"valid\":%s}",
       j?",":"",r.id,(unsigned long long)(uintptr_t)r.hwnd,r.pid,crop.left,crop.top,crop.right,crop.bottom,r.visible?"true":"false",stable?"true":"false",valid?"true":"false");
     }
     std::printf("]}\n");std::fflush(stdout);
    }
   }catch(hresult_error const&e){std::printf("{\"kind\":\"callback_error\",\"hresult\":\"0x%08lX\",\"qpc\":%lld}\n",(unsigned long)e.code(),tick());std::fflush(stdout);failed=true;}
   catch(...){std::printf("{\"kind\":\"callback_error\",\"qpc\":%lld}\n",tick());std::fflush(stdout);failed=true;}
  });
  session.StartCapture();
  std::printf("{\"kind\":\"ready\",\"qpc\":%lld,\"width\":%d,\"height\":%d,\"frame_pool_buffers\":8,\"capture_scope\":\"owned_window\",\"cursor_capture\":false,\"capture_limit_ms\":%llu,\"frame_limit\":%llu}\n",tick(),size.Width,size.Height,limit_ms,frame_limit);std::fflush(stdout);
  auto deadline=GetTickCount64()+limit_ms;
  while(!fs::exists(stop)&&!failed&&!closed&&IsWindow(root)&&GetTickCount64()<deadline)Sleep(5);
  pool.FrameArrived(token);item.Closed(closed_token);
  { std::lock_guard<std::mutex> stop_guard(gate->lock);gate->stopping=true; }
  session.Close();pool.Close();
  std::lock_guard<std::mutex> guard(gate->lock);bool expired=GetTickCount64()>=deadline;
  std::printf("{\"kind\":\"summary\",\"qpc\":%lld,\"frames\":%u,\"changed_images\":%u,\"saved_pixel_bytes\":%llu,\"saved_file_bytes\":%llu,\"deadline_expired\":%s,\"failed\":%s,\"target_closed\":%s,\"frame_census_complete\":false,\"physical_scanout_proven\":false,\"f08_accepted\":false}\n",
   tick(),frames,changed_images,saved_pixel_bytes,saved_bytes,expired?"true":"false",failed?"true":"false",closed?"true":"false");
  return !failed&&!expired&&frames>0?0:1;
 }catch(hresult_error const&e){std::printf("{\"kind\":\"fatal\",\"hresult\":\"0x%08lX\",\"qpc\":%lld}\n",(unsigned long)e.code(),tick());return 1;}
 catch(...){std::printf("{\"kind\":\"fatal\",\"qpc\":%lld}\n",tick());return 1;}
}
