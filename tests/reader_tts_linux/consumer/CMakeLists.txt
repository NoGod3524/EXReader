# SPDX-License-Identifier: MIT
# Consumer of the installed package only: no path into the package source tree.
cmake_minimum_required(VERSION 3.22)
project(reader_tts_consumer LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
find_package(EXReaderTTSLinux 0.1 REQUIRED)
add_executable(reader-tts-consumer consumer.c)
target_include_directories(reader-tts-consumer PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(reader-tts-consumer PRIVATE EXReaderTTSLinux::reader_tts)
if(NOT MSVC)
  target_compile_options(reader-tts-consumer PRIVATE -Wall -Wextra -Werror)
endif()
