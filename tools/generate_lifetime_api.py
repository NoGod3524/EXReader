#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate Debug API boundaries from the public C declarations and layer map.

Internal calls retain their original behavior through implementation aliases;
only calls crossing the public boundary acquire a lifetime scope. Run --check
to verify checked-in generated files after changing public declarations.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"exr_validate", "exr_debug_counts", "exr_debug_cleanup"}
READ_ONLY_STATUS = {
    "exr_audio_locate", "exr_audio_sync_at", "exr_audio_sync_text", "exr_audio_time",
    "exr_fixed_text_find", "exr_fixed_text_select", "exr_fixed_text_hit",
    "exr_fixed_anchor_create", "exr_fixed_anchor_resolve", "exr_document_locate",
    "exr_document_find", "exr_anchor_create", "exr_anchor_resolve", "exr_anchor_resolve_ex",
    "exr_bidi_reorder", "exr_cfi_serialize", "exr_cfi_endpoints", "exr_hit_test",
    "exr_toc_pages_entries", "exr_toc_pages_entry_at", "exr_audio_player_get",
    "exr_document_cfi_point_at", "exr_document_cfi_point_offset",
    "exr_document_cfi_path_create", "exr_document_cfi_path_create_quoted",
    "exr_document_cfi_path_resolve",
    "exr_document_resource", "exr_document_resource_bounded", "exr_document_resolve",
}
SERIALIZED_STATUS = {"exr_library_import_unique", "exr_library_import_source_unique",
                     "exr_library_import_file_unique"}
BORROWED_STRINGS = {
    "exr_node": ("name", "text"), "exr_chapter": ("id", "path"),
    "exr_resource": ("id", "path", "media_type", "properties"),
    "exr_audio_track": ("id", "uri", "media_type"), "exr_audio_chapter": ("id", "title"),
    "exr_audio_sync": ("part_id",), "exr_fixed_page": ("id", "label"),
    "exr_sevenz_entry": ("path",), "exr_metadata_entry": ("key", "value"),
    "exr_dictionary_info": ("bookname", "version", "sametypesequence"),
    "exr_part": ("id", "path", "title"), "exr_target": ("fragment",),
    "exr_footnote": ("id", "label", "text"), "exr_toc_entry": ("title", "target.fragment"),
    "exr_navigation": ("label", "href", "base", "role"),
    "exr_text_hit": ("source", "part"), "exr_font_face_info": ("family", "style_name", "path"),
    "exr_font_skip": ("path", "detail"), "exr_audio_playback": ("track_id",),
}


def borrow_fields(element: str, expression: str, owner: str, indent: str) -> list[str]:
    lines = []
    for field in BORROWED_STRINGS.get(element, ()):
        value = f"({expression})->{field}"
        lines.append(f"{indent}if ({value}) exr_lifetime_borrow({owner}, {value}, strlen({value}) + 1);")
    if element == "exr_node":
        value = f"({expression})->attributes"
        count = f"({expression})->attribute_count"
        lines.append(f"{indent}exr_lifetime_borrow({owner}, {value}, {count} * sizeof(*{value}));")
        lines.append(f"{indent}for (size_t exr_attribute_i__ = 0; exr_attribute_i__ < {count}; exr_attribute_i__++) {{")
        for field in ("name", "value"):
            text = f"{value}[exr_attribute_i__].{field}"
            lines.append(f"{indent}  if ({text}) exr_lifetime_borrow({owner}, {text}, strlen({text}) + 1);")
        lines.append(indent + "}")
    if element in {"exr_hyphen_break", "exr_text_hit", "exr_font_input"}:
        fields = {"exr_hyphen_break": (("before", "before_size"), ("after", "after_size")),
                  "exr_text_hit": (("text", "text_size"),), "exr_font_input": (("data", "size"),)}[element]
        for field, length in fields:
            lines.append(f"{indent}exr_lifetime_borrow({owner}, ({expression})->{field}, ({expression})->{length});")
    return lines


def clean(text: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.S)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Parameter:
    declaration: str
    name: str
    type: str

    @property
    def pointer_output(self) -> bool:
        return self.type.count("*") == 2 and not re.search(r"\*\s*const\s*\*", self.type)

    @property
    def checked(self) -> bool:
        if self.type.count("*") > 1 or self.type == "exr_error *":
            return False
        # Mutable primitive pointers are output slots, not lifetime owners.
        return ("*" in self.type or "[" in self.type) and (
            "const" in self.type or self.type.startswith("exr_")
            or self.type in {"void *", "char *", "unsigned char *"})


def parameter(declaration: str, index: int) -> Parameter:
    declaration = compact(declaration)
    array = re.search(r"\[[^]]*\]\s*$", declaration)
    before_array = declaration[:array.start()].rstrip() if array else declaration
    tail = declaration[array.start():] if array else ""
    match = re.search(r"\b([A-Za-z_]\w*)\s*$", before_array)
    if not match:
        if before_array.endswith("*"):
            name = f"exr_argument_{index}__"
            return Parameter(f"{before_array}{name}{tail}", name, declaration)
        raise ValueError(f"Cannot parse parameter: {declaration}")
    name = match[1]
    prefix = before_array[:match.start()].rstrip()
    # Public headers currently name their parameters. Keep anonymous pointer
    # and scalar declarations supported when a future declaration omits names.
    if not prefix or name in {"const", "void", "size_t", "int", "unsigned", "char", "double", "float"}:
        name = f"exr_argument_{index}__"
        return Parameter(f"{before_array} {name}{tail}", name, declaration)
    return Parameter(declaration, name, compact(prefix + " " + tail))


@dataclass
class Function:
    result: str
    name: str
    parameters: list[Parameter]
    header: str
    layer: str = ""

    @property
    def implementation(self) -> str:
        return "exr_impl_" + self.name.removeprefix("exr_")

    @property
    def signature(self) -> str:
        return ", ".join(p.declaration for p in self.parameters) or "void"

    @property
    def checked(self) -> list[Parameter]:
        return [p for p in self.parameters if p.checked]


def inventory() -> tuple[list[Function], set[str], dict]:
    manifest = json.loads((ROOT / "tools/layers.json").read_text(encoding="utf-8"))
    opaque: set[str] = set()
    functions: list[Function] = []
    for header in sorted((ROOT / "include/exr").glob("*.h")):
        content = clean(header.read_text(encoding="utf-8"))
        opaque.update(re.findall(r"typedef\s+struct\s+(exr_\w+)\s+\1\s*;", content))
        for result, name, arguments in re.findall(
                r"EXR_API\s+([^;]*?)\b(exr_\w+)\s*\(([^;]*?)\)\s*;", content, re.S):
            params = [] if arguments.strip() == "void" else [
                parameter(arg, i) for i, arg in enumerate(arguments.split(","))]
            functions.append(Function(compact(result), name, params,
                                      header.relative_to(ROOT / "include").as_posix()))
    # exr_bitmap has a public body; it must use its true element size.
    opaque.discard("exr_bitmap")
    definitions: dict[str, set[str]] = defaultdict(set)
    sources = {f"src/{name}": layer for name, layer in manifest["files"].items()}
    sources.update({name: layer for name, layer in manifest["headers"].items()
                    if name.startswith("src/")})
    for source, layer in sources.items():
        if Path(source).name.startswith("lifetime_"):
            continue
        content = clean((ROOT / source).read_text(encoding="utf-8"))
        for name in re.findall(r"^\s*(?:[A-Za-z_]\w*\s+|\*\s*)+(exr_\w+)\s*\([^;{}]*\)\s*\{",
                               content, re.M):
            definitions[name].add(layer)
    for function in functions:
        owners = definitions[function.name]
        if len(owners) != 1:
            raise ValueError(f"Expected one implementation layer for {function.name}: {owners}")
        function.layer = next(iter(owners))
    return functions, opaque, manifest


def emit(function: Function, opaque: set[str]) -> str:
    checked = function.checked
    checked_values = [p.name for p in checked]
    checked_structs = []
    for p in function.parameters:
        if p.type == "const exr_bitmap *" or (p.type == "exr_bitmap *" and function.name == "exr_bitmap_free"):
            checked_structs.append(p.name)
            checked_values.append(f"({p.name} ? {p.name}->pixels : NULL)")
        if p.type in {"const exr_fixed_open_options *", "const exr_pdf_form_write_options *"}:
            checked_structs.append(p.name)
            typename = p.type.removeprefix("const ").rstrip(" *")
            field = "fallback_font" if typename == "exr_fixed_open_options" else "font"
            checked_values.append(f"({p.name} && {p.name}->struct_size >= offsetof({typename}, {field}) "
                                  f"+ sizeof({p.name}->{field}) ? {p.name}->{field} : NULL)")
    owner = next((p for p in checked if re.search(r"\bexr_\w+\b", p.type)), None)
    borrowed = function.result.startswith("const ") and "*" in function.result and owner
    count = next((p for p in function.parameters if p.type == "size_t *"), None) if borrowed else None
    lines = [f"{function.result} {function.implementation}({function.signature});",
             f"{function.result} {function.name}({function.signature}) {{",
             "  exr_lifetime_scope exr_scope__;"]
    for value in checked_structs:
        lines.append(f"  (void)exr_validate({value});")
    lines.append("  const void *exr_arguments__[] = {" + ", ".join(checked_values) + "};")
    if count:
        lines.append("  size_t exr_count__ = 0;")
    if function.result != "void":
        lines.append(f"  {function.result} exr_result__;")
    if function.name == "exr_dictionary_query":
        lines.append("  size_t exr_dictionary_index__;")
        lines.append("  if (dictionaries && count <= 64)")
        lines.append("    for (exr_dictionary_index__ = 0; exr_dictionary_index__ < count; exr_dictionary_index__++)")
        lines.append("      (void)exr_validate(dictionaries[exr_dictionary_index__]);")
    for p in checked:
        typename = compact(p.type.replace("*", "").removeprefix("const "))
        if typename in opaque:
            lines.append(f'  exr_lifetime_expect({p.name}, "{typename}");')
    if function.name == "exr_free":
        lines.append(f'  exr_lifetime_expect({checked[0].name}, "buffer");')
    if function.result == "void":
        mode = 2
    elif function.name in SERIALIZED_STATUS:
        mode = 3
    elif function.result != "exr_status" or function.name in READ_ONLY_STATUS or any(
            p.type == "const exr_font_manager *" for p in function.parameters):
        mode = 1
    else:
        mode = 0
    lines.append(f"  if (!exr_lifetime_begin(&exr_scope__, exr_arguments__, {len(checked_values)}, {mode})) {{")
    if function.result == "exr_status":
        if function.name == "exr_hyphenator_breaks":
            lines.append("    if (breaks && size <= 1024) memset(breaks, 0, size + 1);")
        if function.name == "exr_stretch_get":
            lines.append("    if (out) memset(out, 0, sizeof(*out));")
        if function.name in SERIALIZED_STATUS:
            lines.append("    if (id) *id = 0;")
            lines.append("    if (created) *created = 0;")
        for p in function.parameters:
            if p.pointer_output:
                lines.append(f"    if ({p.name}) *{p.name} = NULL;")
            elif p.type == "size_t *" and re.search(r"count|size|read|written|accepted", p.name):
                lines.append(f"    if ({p.name}) *{p.name} = 0;")
        error = next((p.name for p in function.parameters if p.type == "exr_error *"), "NULL")
        lines.append(f'    return exr_fail({error}, EXR_ARGUMENT, "Reentrant SDK operation");')
    elif function.result == "void":
        lines.append("    return;")
    else:
        # Getter mode permits nested observation, so this branch is unreachable.
        lines.append("    abort();")
    lines.append("  }")
    if function.result == "void" and function.name.endswith(("_free", "_close")):
        for p in function.parameters:
            if compact(p.type.replace("*", "")) in opaque and p.type.count("*") == 1:
                lines.append(f"  exr_lifetime_release_public({p.name});")
    call_arguments = []
    for p in function.parameters:
        call_arguments.append(f"{p.name} ? {p.name} : &exr_count__" if p is count else p.name)
    call = f"{function.implementation}({', '.join(call_arguments)})"
    lines.append(f"  {'exr_result__ = ' if function.result != 'void' else ''}{call};")
    if function.result == "exr_status":
        exposed = []
        for p in function.parameters:
            element = compact(p.type.replace("*", "").removeprefix("const "))
            following = function.parameters[function.parameters.index(p) + 1:]
            extent = next((item for item in following + function.parameters
                           if item.type == "size_t *" and re.search(r"count|size", item.name)), None)
            length = f"({extent.name} ? *{extent.name} : 1)" if extent else "1"
            if p.pointer_output and element in opaque and "const" in p.type and owner:
                exposed.append(f"    if ({p.name}) exr_lifetime_loan({owner.name}, *{p.name});")
            elif p.pointer_output and element not in opaque:
                if element == "char":
                    size = f"{length} + 1" if extent and "const" in p.type else f"*{p.name} ? strlen(*{p.name}) + 1 : 0"
                else:
                    unit = "1" if element == "void" else f"sizeof(**{p.name})"
                    size = f"{length} * {unit}"
                if "const" not in p.type:
                    exposed.append(f"    if ({p.name}) exr_lifetime_own(*{p.name}, {size});")
                elif owner:
                    exposed.append(f"    if ({p.name}) exr_lifetime_borrow({owner.name}, *{p.name}, {size});")
                    fields = borrow_fields(element, f"*{p.name} + exr_borrow_i__", owner.name, "      ")
                    if fields:
                        exposed.append(f"    if ({p.name} && *{p.name}) for (size_t exr_borrow_i__ = 0; exr_borrow_i__ < {length}; exr_borrow_i__++) {{")
                        exposed.extend(fields)
                        exposed.append("    }")
            elif p.type == "exr_bitmap *":
                exposed.append(f"    if ({p.name}) exr_lifetime_own({p.name}->pixels, "
                               f"(size_t){p.name}->stride * {p.name}->height);")
            elif p.type == "exr_glyph_image *":
                exposed.append(f"    if ({p.name}) exr_lifetime_own({p.name}->bitmap.pixels, "
                               f"(size_t){p.name}->bitmap.stride * {p.name}->bitmap.height);")
            elif p.type.count("*") == 1 and "const" not in p.type and owner:
                fields = borrow_fields(element, p.name, owner.name, "      ")
                if fields:
                    exposed.append(f"    if ({p.name}) {{")
                    exposed.extend(fields)
                    exposed.append("    }")
        if exposed:
            lines.append("  if (exr_result__ == EXR_OK) {")
            lines.extend(exposed)
            lines.append("  }")
    if borrowed:
        assert owner is not None
        element = compact(function.result.removeprefix("const ").replace("*", ""))
        if element == "char":
            size = f"({count.name} ? *{count.name} : exr_count__) + 1" if count else "exr_result__ ? strlen(exr_result__) + 1 : 0"
        else:
            unit = "1" if element == "void" or element in opaque else "sizeof(*exr_result__)"
            size = f"({count.name} ? *{count.name} : exr_count__) * {unit}" if count else unit
        if element in opaque:
            lines.append(f"  exr_lifetime_loan({owner.name}, exr_result__);")
        else:
            lines.append(f"  exr_lifetime_borrow({owner.name}, exr_result__, {size});")
        if element == "exr_bitmap":
            lines.append(f"  if (exr_result__) exr_lifetime_borrow({owner.name}, exr_result__->pixels, "
                         "(size_t)exr_result__->stride * exr_result__->height);")
        fields = borrow_fields(element, "exr_result__ + exr_borrow_i__", owner.name, "    ")
        if fields:
            length = f"({count.name} ? *{count.name} : exr_count__)" if count else "1"
            lines.append(f"  if (exr_result__) for (size_t exr_borrow_i__ = 0; exr_borrow_i__ < {length}; exr_borrow_i__++) {{")
            lines.extend(fields)
            lines.append("  }")
        for p in function.parameters:
            if p.type == "const char **":
                lines.append(f"  if ({p.name} && *{p.name}) exr_lifetime_borrow({owner.name}, *{p.name}, strlen(*{p.name}) + 1);")
    if function.name == "exr_font_manager_skip":
        lines.append("  if (exr_result__ && out) {")
        lines.extend(borrow_fields("exr_font_skip", "out", "manager", "    "))
        lines.append("  }")
    if function.name == "exr_layout_font":
        lines.append("  exr_lifetime_view(layout, exr_result__);")
    lines.append("  exr_lifetime_end(&exr_scope__);")
    if function.result != "void":
        lines.append("  return exr_result__;")
    return "\n".join(lines + ["}", ""])


def outputs() -> tuple[dict[Path, str], dict]:
    functions, opaque, manifest = inventory()
    selected = [f for f in functions if f.name not in EXCLUDED and f.checked]
    by_layer: dict[str, list[Function]] = defaultdict(list)
    for function in selected:
        by_layer[function.layer].append(function)
    result = {}
    intro = "/* SPDX-License-Identifier: MIT */\n/* Generated by tools/generate_lifetime_api.py; do not edit. */\n"
    for layer, layer_functions in sorted(by_layer.items()):
        headers = sorted({f.header for f in layer_functions} - {"exr/base.h"})
        content = intro + '#include "base_internal.h"\n'
        content += "\n".join(f'#include "{header}"' for header in headers) + "\n#ifndef NDEBUG\n\n"
        content += "\n".join(emit(f, opaque) for f in sorted(layer_functions, key=lambda f: f.name))
        content += "\n#endif\n"
        result[ROOT / "src" / f"lifetime_api_{layer}.c"] = content
    rename = intro + "#ifndef EXR_LIFETIME_RENAME_H\n#define EXR_LIFETIME_RENAME_H\n"
    rename += "#if !defined(NDEBUG) && defined(EXR_LIFETIME_IMPLEMENTATION) && !defined(EXR_LIFETIME_WRAPPER)\n"
    rename += "\n".join(f"#define {f.name} {f.implementation}" for f in sorted(selected, key=lambda f: f.name))
    rename += "\n#endif\n#endif\n"
    result[ROOT / "src/lifetime_rename.h"] = rename
    report = {"public_functions": len(functions), "wrapped_functions": len(selected),
              "layers": {layer: len(items) for layer, items in sorted(by_layer.items())}}
    return result, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files, report = outputs()
    stale = []
    for path, content in files.items():
        previous = path.read_text(encoding="utf-8") if path.exists() else None
        if args.check:
            if previous != content:
                stale.append(str(path.relative_to(ROOT)))
        elif previous != content:
            path.write_text(content, encoding="utf-8", newline="\n")
    print(json.dumps(report, sort_keys=True))
    if stale:
        print("Stale generated lifetime boundaries: " + ", ".join(stale))
    return bool(stale)


if __name__ == "__main__":
    raise SystemExit(main())
