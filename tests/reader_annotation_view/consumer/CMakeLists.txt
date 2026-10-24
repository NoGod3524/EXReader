# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderAnnotationViewInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: frozen SDK stage, product catalog, revisions,
# reading-state adapter and the optional annotation-view package.
find_package(EXReaderAnnotationView 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
add_executable(annotation-view-probe probe.cpp)
target_link_libraries(annotation-view-probe PRIVATE EXReaderAnnotationView::reader_annotation_view
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite
  EXReader::exr_library Threads::Threads)
if(MSVC)
  target_link_options(annotation-view-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/annotation-view-link.map")
elseif(APPLE)
  target_link_options(annotation-view-probe PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/annotation-view-link.map")
else()
  target_link_options(annotation-view-probe PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/annotation-view-link.map")
endif()
add_executable(annotation-view-c-consumer api.c)
set_target_properties(annotation-view-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(annotation-view-c-consumer PRIVATE EXReaderAnnotationView::reader_annotation_view
  EXReaderProductCatalog::reader_catalog_sqlite Threads::Threads)
