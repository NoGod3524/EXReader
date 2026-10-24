# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderSyncResilienceConsumer LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
add_executable(resilience-consumer main.cpp)
# EXReaderSession publicly carries the installed sync, revisions and WebDAV
# dependencies, so both modes link the same installed package graph.
target_link_libraries(resilience-consumer PRIVATE EXReaderSession::reader_session)
if(WIN32)
  target_link_libraries(resilience-consumer PRIVATE shell32)
endif()
