"""Small ctypes binding to the public exr/edit.h and exr/formats.h APIs."""
# SPDX-License-Identifier: MIT
import ctypes as c
import os

ID = c.c_uint64


class RunProps(c.Structure):
    _fields_ = [('present', c.c_uint32), ('font', c.c_char * 128), ('size', c.c_uint32),
                ('color', c.c_uint32), ('bold', c.c_uint), ('italic', c.c_uint)]


class ParaProps(c.Structure):
    _fields_ = [('present', c.c_uint32), ('align', c.c_int), ('left', c.c_int32),
                ('right', c.c_int32), ('first', c.c_int32), ('before', c.c_uint32),
                ('after', c.c_uint32), ('line', c.c_uint32), ('rule', c.c_int),
                ('keep_next', c.c_uint), ('keep_lines', c.c_uint), ('page_before', c.c_uint),
                ('numbering', c.c_uint32), ('level', c.c_uint32)]


class Run(c.Structure):
    _fields_ = [('id', ID), ('kind', c.c_int), ('text', c.c_void_p), ('length', c.c_size_t),
                ('props', RunProps), ('xml', c.c_void_p), ('xml_size', c.c_size_t)]


class Block(c.Structure):
    _fields_ = [('id', ID), ('section', ID), ('kind', c.c_int), ('props', ParaProps),
                ('runs', c.POINTER(Run)), ('count', c.c_size_t),
                ('xml', c.c_void_p), ('xml_size', c.c_size_t)]


class Section(c.Structure):
    _fields_ = [('id', ID)] + [(n, c.c_int32) for n in
        ('width', 'height', 'top', 'right', 'bottom', 'left', 'header', 'footer')] + [
        ('landscape', c.c_uint), ('headers', (c.c_char * 128) * 3), ('footers', (c.c_char * 128) * 3)]


class Error(c.Structure):
    _fields_ = [('code', c.c_int), ('message', c.c_char * 256)]


def ok(status, operation, error=None):
    if status:
        detail = error.message.decode('utf-8', errors='replace') if error else ''
        raise RuntimeError(f'{operation}: engine status={status} {detail}')


class Engine:
    def __init__(self, library):
        self.directory = os.add_dll_directory(str(library.parent)) if os.name == 'nt' else None
        self.dll = c.CDLL(str(library))
        ptr, size = c.c_void_p, c.c_size_t
        signatures = [
            ('docx_open', c.c_int, [c.c_char_p, ptr, c.POINTER(ptr), c.POINTER(Error)]),
            ('docx_write', c.c_int, [ptr, c.POINTER(ptr), c.POINTER(size), c.POINTER(Error)]),
            ('doc_free', None, [ptr]), ('block_count', size, [ptr]),
            ('block_at', c.POINTER(Block), [ptr, size]),
            ('sections', c.POINTER(Section), [ptr, c.POINTER(size)]),
            ('insert_paragraph', c.c_int, [ptr, ID, c.POINTER(Run), size, c.POINTER(ParaProps), c.POINTER(ID)]),
            ('set_paragraph_props', c.c_int, [ptr, ID, c.POINTER(ParaProps)]),
            ('set_run_props', c.c_int, [ptr, ID, size, c.POINTER(RunProps)]),
            ('split_paragraph', c.c_int, [ptr, ID, size, size]),
            ('delete_block', c.c_int, [ptr, ID]), ('undo', c.c_int, [ptr])]
        for name, result, args in signatures:
            symbol = 'exr_edit_' + name
            try:
                fn = getattr(self.dll, symbol)
            except AttributeError as exc:
                raise RuntimeError(f'{library}: missing {symbol}; X1 editable DOCX bridge is required') from exc
            fn.restype, fn.argtypes = result, args
            setattr(self, name, fn)
        self.free = self.dll.exr_free
        self.free.restype, self.free.argtypes = None, [ptr]

    def open(self, path):
        doc, error = c.c_void_p(), Error()
        ok(self.docx_open(str(path).encode('utf-8'), None, c.byref(doc), c.byref(error)),
           f'open {path}', error)
        if not doc:
            raise RuntimeError(f'open {path}: successful status with NULL document')
        return doc

    def save(self, doc, path):
        data, size, error = c.c_void_p(), c.c_size_t(), Error()
        try:
            ok(self.docx_write(doc, c.byref(data), c.byref(size), c.byref(error)),
               f'save {path}', error)
            if not data or not size.value:
                raise RuntimeError(f'save {path}: empty DOCX output')
            path.write_bytes(c.string_at(data, size.value))
        finally:
            if data:
                self.free(data)

    def blocks(self, doc):
        return [self.block_at(doc, i).contents for i in range(self.block_count(doc))]

    def paragraphs(self, doc):
        return [block for block in self.blocks(doc) if block.kind == 0]

    def insert(self, doc, anchor, text):
        storage = c.create_string_buffer(text.encode('utf-8'))
        run = Run(text=c.cast(storage, c.c_void_p), length=len(text.encode('utf-8')),
                  props=RunProps(present=3, font=b'Times New Roman', size=24))
        props, new_id = ParaProps(present=4, line=480), ID()
        ok(self.insert_paragraph(doc, anchor, c.byref(run), 1, c.byref(props), c.byref(new_id)),
           f'insert paragraph {text!r}')
        if not new_id.value:
            raise RuntimeError('insert paragraph: successful status with zero ID')
        return new_id.value


def text(block):
    return ''.join(c.string_at(run.text, run.length).decode('utf-8')
                   for run in block.runs[:block.count] if run.kind == 0)
