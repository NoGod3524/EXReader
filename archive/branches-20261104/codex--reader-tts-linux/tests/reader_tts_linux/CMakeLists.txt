# SPDX-License-Identifier: MIT
# Source build of the fault-injection suite. The library is compiled from the
# package tree with READER_TTS_BUILD_TEST_HOOKS=ON; the installed package used by
# the consumers never contains these hooks.
cmake_minimum_required(VERSION 3.22)
project(reader_tts_linux_suite LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(READER_TTS_BUILD_TEST_HOOKS ON CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../../extras/reader-tts-linux"
                 "${CMAKE_CURRENT_BINARY_DIR}/pkg")
add_executable(tts-hook-suite tts_hook_suite.c)
target_include_directories(tts-hook-suite PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")
target_link_libraries(tts-hook-suite PRIVATE EXReaderTTSLinux::reader_tts)
if(NOT MSVC)
  target_compile_options(tts-hook-suite PRIVATE -Wall -Wextra -Werror)
endif()
