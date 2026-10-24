# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderOpdsBrowserInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: the OPDS browser package (which carries the frozen OPDS
# module) plus the SDK library and sideload packages it was installed against.
find_package(EXReaderOpdsBrowser 0.1.0 EXACT CONFIG REQUIRED)
add_executable(opds-consumer consumer.c)
target_link_libraries(opds-consumer PRIVATE EXReaderOpdsBrowser::reader_opds_browser)
add_executable(opds-import-consumer consumer.cpp)
target_link_libraries(opds-import-consumer PRIVATE EXReaderOpdsBrowser::reader_opds_import)
