# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_keyboard_actions_consumers LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  # Keep the CMake default runtime so the installed static library, which uses the
  # default runtime as well, links without a RuntimeLibrary mismatch.
  add_compile_options(/utf-8)
endif()

# Only the installed packages are consumed. No source or build include directory
# of apps/reader/keyboard-actions is on this project's include path, so a target
# that compiles against a working copy instead of the install prefix fails here.
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderKeyboardActions 0.1.0 EXACT CONFIG REQUIRED)

add_executable(keyboard-c-consumer c_consumer.c)
target_link_libraries(keyboard-c-consumer PRIVATE EXReaderKeyboardActions::reader_keyboard_actions)

add_executable(keyboard-cpp-consumer cxx_consumer.cpp)
target_link_libraries(keyboard-cpp-consumer PRIVATE EXReaderKeyboardActions::reader_keyboard_actions)
if(UNIX)
  find_package(Threads REQUIRED)
  target_link_libraries(keyboard-cpp-consumer PRIVATE Threads::Threads)
endif()

if(MSVC)
  target_compile_options(keyboard-c-consumer PRIVATE /W4 /WX)
  target_compile_options(keyboard-cpp-consumer PRIVATE /W4 /WX)
else()
  target_compile_options(keyboard-c-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(keyboard-cpp-consumer PRIVATE -Wall -Wextra -Werror)
endif()
