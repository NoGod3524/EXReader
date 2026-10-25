# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderCloudImport VERSION 0.1.0 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
# Only installed public packages: the SDK, sideload and the WebDAV source.
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderWebDAV CONFIG REQUIRED)
add_library(reader_cloud_import STATIC src/cloud_import.c)
target_include_directories(reader_cloud_import PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_cloud_import PUBLIC
  EXReader::exr_library EXReaderSideload::exr_sideload EXReaderWebDAV::exr_webdav)
set_target_properties(reader_cloud_import PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(MSVC)
  target_compile_options(reader_cloud_import PRIVATE /W4 /WX)
  target_compile_definitions(reader_cloud_import PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_cloud_import PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_cloud_import EXPORT EXReaderCloudImportTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_cloud_import.h DESTINATION include)
install(EXPORT EXReaderCloudImportTargets NAMESPACE EXReaderCloudImport:: DESTINATION lib/cmake/EXReaderCloudImport)
configure_package_config_file(EXReaderCloudImportConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderCloudImport)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderCloudImport)
