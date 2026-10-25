# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderJumpHistoryInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: the jump-history package pulls the installed
# reading-state adapter, the frozen SDK, the unchanged revision module and the
# one product catalog provider.
find_package(Threads REQUIRED)
find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
add_executable(jump-history-probe probe.cpp)
target_link_libraries(jump-history-probe PRIVATE EXReaderJumpHistory::reader_jump_history Threads::Threads
  EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
add_executable(jump-history-c-consumer api.c)
set_target_properties(jump-history-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(jump-history-c-consumer PRIVATE EXReaderJumpHistory::reader_jump_history Threads::Threads)
