# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderThumbnails VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Optional package. Only installed frozen SDK components are used: core (image
# decode, fixed render) and library (exr_library_blob). No SDK private header,
# SQL, product catalog or revision store is involved.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0/3.42.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_library(reader_thumbnails STATIC src/thumbnails.cpp)
target_include_directories(reader_thumbnails PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_thumbnails PUBLIC EXReader::exr_core EXReader::exr_library)
if(MSVC)
  target_compile_options(reader_thumbnails PRIVATE /W4 /WX)
else()
  target_compile_options(reader_thumbnails PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_thumbnails EXPORT EXReaderThumbnailsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_thumbnails.h DESTINATION include)
install(EXPORT EXReaderThumbnailsTargets NAMESPACE EXReaderThumbnails:: DESTINATION lib/cmake/EXReaderThumbnails)
configure_package_config_file(EXReaderThumbnailsConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderThumbnailsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderThumbnails)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderThumbnailsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderThumbnailsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderThumbnailsConfigVersion.cmake" DESTINATION lib/cmake/EXReaderThumbnails)
