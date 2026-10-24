# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderUnicodeInteropConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
find_package(EXReaderCommands 0.1.0 EXACT CONFIG REQUIRED)

add_executable(unicode-consumer probe.cpp)
target_link_libraries(unicode-consumer PRIVATE
  EXReaderCommands::reader_commands
  EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(unicode-consumer PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/unicode-link.map")
  target_link_libraries(unicode-consumer PRIVATE shell32)
elseif(APPLE)
  target_link_options(unicode-consumer PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/unicode-link.map")
else()
  target_link_options(unicode-consumer PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/unicode-link.map"
    "-Wl,--trace-symbol=sqlite3_open_v2")
endif()

# The same observable behaviour through the installed C ABI header only.
add_executable(unicode-c-consumer api.c)
set_target_properties(unicode-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(unicode-c-consumer PRIVATE
  EXReaderCommands::reader_commands
  EXReaderProductCatalog::reader_catalog_sqlite)
if(MSVC)
  target_link_options(unicode-c-consumer PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/unicode-c-link.map")
  target_link_libraries(unicode-c-consumer PRIVATE shell32)
endif()
