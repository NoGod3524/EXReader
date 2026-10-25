# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderNextS16InstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only. S16_RAW selects the explicit raw candidate install
# (EXReaderJumpHistory 0.2.0); the default consumer asks for 0.1.0, so a mixed
# install can never be configured by accident.
option(S16_RAW "Consume the explicit raw candidate install" OFF)
find_package(Threads REQUIRED)
if(S16_RAW)
  find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)
else()
  find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
endif()
add_executable(s16-c-consumer api.c)
set_target_properties(s16-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(s16-c-consumer PRIVATE EXReaderJumpHistory::reader_jump_history Threads::Threads)
if(S16_RAW)
  add_executable(s16-raw-probe probe.cpp)
  target_link_libraries(s16-raw-probe PRIVATE EXReaderJumpHistory::reader_jump_history Threads::Threads
    EXReaderProductCatalog::reader_catalog EXReaderProductCatalog::reader_catalog_sqlite)
endif()
