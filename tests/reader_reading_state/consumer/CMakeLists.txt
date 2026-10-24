# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderReadingStateInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: frozen SDK stage, product catalog, revisions, adapter.
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_executable(reading-state-probe probe.cpp)
# The one installed product SQLite provider is linked explicitly; the map below
# records which archive supplied sqlite3_open_v2 for both SDK and product calls.
target_link_libraries(reading-state-probe PRIVATE EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(reading-state-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/reading-state-link.map")
else()
  target_link_options(reading-state-probe PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/reading-state-link.map" "-Wl,--trace-symbol=sqlite3_open_v2")
endif()
add_executable(reading-state-c-consumer api.c)
set_target_properties(reading-state-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(reading-state-c-consumer PRIVATE EXReaderReadingState::reader_reading_state)
