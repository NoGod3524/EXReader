# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderAnnotationExportConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: the optional export package (which brings the
# unchanged revision store, reading-state decoder and frozen SDK).
find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
add_executable(annotation-export-c-consumer api.c)
set_target_properties(annotation-export-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(annotation-export-c-consumer PRIVATE EXReaderAnnotationExport::reader_annotation_export
  EXReaderProductCatalog::reader_catalog_sqlite)
add_executable(annotation-export-probe probe.cpp)
target_link_libraries(annotation-export-probe PRIVATE EXReaderAnnotationExport::reader_annotation_export
  EXReaderProductCatalog::reader_catalog_sqlite Threads::Threads)
if(MSVC)
  target_link_options(annotation-export-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/annotation-export-link.map")
elseif(APPLE)
  target_link_options(annotation-export-probe PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/annotation-export-link.map")
else()
  target_link_options(annotation-export-probe PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/annotation-export-link.map")
endif()
