# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderOCROverlayInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: the overlay package resolves the frozen SDK core and the
# optional OCR adapter through its own config file; nothing is added from the tree.
find_package(EXReaderOCROverlay 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
add_executable(reader-ocr-overlay-probe probe.cpp)
target_link_libraries(reader-ocr-overlay-probe PRIVATE EXReaderOCROverlay::reader_ocr_overlay Threads::Threads)
# A pure C consumer proves the public header is usable without C++ headers.
add_executable(reader-ocr-overlay-c-consumer api.c)
set_target_properties(reader-ocr-overlay-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(reader-ocr-overlay-c-consumer PRIVATE EXReaderOCROverlay::reader_ocr_overlay)
