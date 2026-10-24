# SPDX-License-Identifier: MIT
# C++ consumer of the installed package only.
cmake_minimum_required(VERSION 3.22)
project(reader_tts_consumer_cpp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(EXReaderTTSLinux 0.1 REQUIRED)
add_executable(reader-tts-consumer-cpp consumer_cpp.cpp)
target_include_directories(reader-tts-consumer-cpp PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/..")
target_link_libraries(reader-tts-consumer-cpp PRIVATE EXReaderTTSLinux::reader_tts)
if(NOT MSVC)
  target_compile_options(reader-tts-consumer-cpp PRIVATE -Wall -Wextra -Werror)
endif()
