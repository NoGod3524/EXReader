# SPDX-License-Identifier: MIT
# Reuse the unchanged account capture probe with the Wave3 installed adapter.
cmake_minimum_required(VERSION 3.24)
project(TerraWindowsSyncCapture LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderReadingState 0.2.0 EXACT CONFIG REQUIRED)
add_executable(reading-capture-probe ../../reader_windows_account/consumer/probe.cpp)
target_link_libraries(reading-capture-probe PRIVATE EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(reading-capture-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/reading-capture-link.map")
endif()
