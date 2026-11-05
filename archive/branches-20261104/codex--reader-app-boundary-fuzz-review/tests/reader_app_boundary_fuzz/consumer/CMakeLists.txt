# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderAppBoundaryFuzzConsumers LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# Installed packages only: no source directory, no SDK private header, no second
# SQLite build. The sanitizer flags come from the workflow through CMAKE_*_FLAGS.
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)

add_executable(boundary-c-consumer boundary_c_consumer.c)
target_link_libraries(boundary-c-consumer PRIVATE
  EXReaderPreferences::reader_preferences
  EXReaderRevisions::reader_revisions
  EXReaderProductCatalog::reader_catalog_sqlite)
set_target_properties(boundary-c-consumer PROPERTIES LINKER_LANGUAGE CXX)

add_executable(boundary-cpp-consumer boundary_cpp_consumer.cpp)
target_link_libraries(boundary-cpp-consumer PRIVATE
  EXReaderPreferences::reader_preferences
  EXReaderReadingState::reader_reading_state)

if(MSVC)
  target_compile_options(boundary-c-consumer PRIVATE /W4 /WX)
  target_compile_options(boundary-cpp-consumer PRIVATE /W4 /WX)
else()
  target_compile_options(boundary-c-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(boundary-cpp-consumer PRIVATE -Wall -Wextra -Werror)
endif()
