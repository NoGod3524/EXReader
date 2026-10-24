# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderLibraryHealthInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: no source-tree include directory is added here.
find_package(EXReaderLibraryHealth 1.0.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
add_executable(library-health-probe library_health_probe.c)
target_link_libraries(library-health-probe PRIVATE
  EXReaderLibraryHealth::reader_library_health Threads::Threads)
if(WIN32)
  target_link_libraries(library-health-probe PRIVATE psapi)
endif()
add_executable(library-health-cpp-consumer library_health_cpp_consumer.cpp)
target_link_libraries(library-health-cpp-consumer PRIVATE
  EXReaderLibraryHealth::reader_library_health Threads::Threads)
