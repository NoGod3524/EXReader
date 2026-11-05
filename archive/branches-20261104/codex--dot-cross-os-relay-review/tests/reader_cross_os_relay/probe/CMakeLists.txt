# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderCrossOsRelayProbe LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: frozen SDK stage, product catalog, revisions,
# reading adapter, native sync/WebDAV and original export.
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSync 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSideload CONFIG REQUIRED)
add_executable(relay-probe probe.cpp)
target_link_libraries(relay-probe PRIVATE EXReaderReadingState::reader_reading_state
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite
  EXReaderSync::reader_sync EXReaderSideload::exr_sideload)
if(MSVC)
  target_link_options(relay-probe PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/relay-link.map")
elseif(APPLE)
  target_link_options(relay-probe PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/relay-link.map")
else()
  target_link_options(relay-probe PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/relay-link.map")
endif()
