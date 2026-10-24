cmake_minimum_required(VERSION 3.24)
project(ReaderThumbnailsInstalledConsumer LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed packages only: the optional thumbnails package and the frozen SDK
# (core + pdf + library are used directly by the consumers to build sources).
find_package(EXReaderThumbnails 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core pdf library)
find_package(Threads REQUIRED)
add_library(thumb-peak STATIC peak.c)
add_executable(thumb-c-consumer api.c)
set_target_properties(thumb-c-consumer PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(thumb-c-consumer PRIVATE EXReaderThumbnails::reader_thumbnails)
add_executable(thumb-probe probe.cpp)
target_link_libraries(thumb-probe PRIVATE EXReaderThumbnails::reader_thumbnails EXReader::exr_pdf EXReader::exr_library
  thumb-peak Threads::Threads)
if(WIN32)
  target_link_libraries(thumb-probe PRIVATE psapi)
endif()
# Regression consumer for the four review findings: it only uses the public ABI that
# existed at the reviewed source, so it builds against both the unfixed and fixed library.
add_executable(thumb-regress regress.cpp)
target_link_libraries(thumb-regress PRIVATE EXReaderThumbnails::reader_thumbnails)
# Fault-injection consumer: replaces the global operator new/delete inside its own
# binary to make the n-th allocation fail.
add_executable(thumb-fault fault.cpp)
target_link_libraries(thumb-fault PRIVATE EXReaderThumbnails::reader_thumbnails EXReader::exr_library)
