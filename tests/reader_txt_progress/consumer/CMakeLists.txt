# SPDX-License-Identifier: MIT
# Independent installed consumer for the TXT position module.
cmake_minimum_required(VERSION 3.24)
project(EXReaderTxtProgressProbe LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderTxtProgress 0.1.0 EXACT CONFIG REQUIRED)
add_executable(txtp-probe main.cpp)
target_link_libraries(txtp-probe PRIVATE EXReaderTxtProgress::reader_txt_progress)

add_executable(txtp-inject inject.cpp)
target_link_libraries(txtp-inject PRIVATE EXReaderTxtProgress::reader_txt_progress)
