import ctypes as c, os, sys, zlib, struct
sys.path.insert(0, 'tools')
from benchmark_pdf_blend import Bitmap, Error
from benchmark_pdf_rect import Page
lib, pdf, page_no, width, outp = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
os.add_dll_directory(os.path.dirname(os.path.abspath(lib)))
e = c.CDLL(os.path.abspath(lib))
e.exr_fixed_open.argtypes = [c.c_char_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(Error)]
e.exr_fixed_pages.argtypes = [c.c_void_p, c.POINTER(c.c_size_t)]; e.exr_fixed_pages.restype = c.POINTER(Page)
e.exr_fixed_render.argtypes = [c.c_void_p, c.c_size_t, c.c_double, c.c_void_p, c.POINTER(Bitmap), c.POINTER(Error)]
err = Error(); d = c.c_void_p(); assert not e.exr_fixed_open(pdf.encode(), None, c.byref(d), c.byref(err))
n = c.c_size_t(); g = e.exr_fixed_pages(d, c.byref(n))[page_no - 1].geometry
b = Bitmap(); assert not e.exr_fixed_render(d, page_no - 1, width / ((g.bounds[2] - g.bounds[0]) * g.unit_scale), None, c.byref(b), c.byref(err))
raw = b''.join(b'\0' + c.string_at(b.pixels + y * b.stride, b.width * 4) for y in range(b.height))
chunk = lambda t, data: struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data))
open(outp, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', b.width, b.height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
