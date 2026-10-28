# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderLocalDownloads VERSION 0.1.0 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
# Only installed public packages: the SDK, sideload and the product catalog.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0/3.42.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderProductCatalog 0.1.0 CONFIG REQUIRED)
add_library(reader_local_downloads STATIC src/local_downloads.c)
target_include_directories(reader_local_downloads PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_local_downloads PUBLIC
  EXReader::exr_library EXReaderSideload::exr_sideload EXReaderProductCatalog::reader_catalog)
set_target_properties(reader_local_downloads PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(MSVC)
  target_compile_options(reader_local_downloads PRIVATE /W4 /WX)
  target_compile_definitions(reader_local_downloads PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_local_downloads PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_local_downloads EXPORT EXReaderLocalDownloadsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_local_downloads.h DESTINATION include)
install(EXPORT EXReaderLocalDownloadsTargets NAMESPACE EXReaderLocalDownloads:: DESTINATION lib/cmake/EXReaderLocalDownloads)
configure_package_config_file(EXReaderLocalDownloadsConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalDownloadsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderLocalDownloads)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalDownloadsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalDownloadsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalDownloadsConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderLocalDownloads)
