# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderBatchImport VERSION 0.1.0 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
# Only the installed public SDK and the installed sideload package.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0/3.42.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
add_library(reader_batch_import STATIC src/batch_import.c)
target_include_directories(reader_batch_import PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_batch_import PUBLIC
  EXReader::exr_library EXReaderSideload::exr_sideload)
set_target_properties(reader_batch_import PROPERTIES
  C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(MSVC)
  target_compile_options(reader_batch_import PRIVATE /W4 /WX)
  target_compile_definitions(reader_batch_import PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_batch_import PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_batch_import EXPORT EXReaderBatchImportTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_batch_import.h DESTINATION include)
install(EXPORT EXReaderBatchImportTargets NAMESPACE EXReaderBatchImport:: DESTINATION lib/cmake/EXReaderBatchImport)
configure_package_config_file(EXReaderBatchImportConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBatchImportConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderBatchImport)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderBatchImportConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBatchImportConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBatchImportConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderBatchImport)
