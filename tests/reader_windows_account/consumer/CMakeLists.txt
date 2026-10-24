# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderWindowsAccountCaptureConsumer LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: reading-state adapter, product catalog and revisions.
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_executable(reading-capture-probe probe.cpp)
target_link_libraries(reading-capture-probe PRIVATE EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(reading-capture-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/reading-capture-link.map")
else()
  target_link_options(reading-capture-probe PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/reading-capture-link.map")
endif()
