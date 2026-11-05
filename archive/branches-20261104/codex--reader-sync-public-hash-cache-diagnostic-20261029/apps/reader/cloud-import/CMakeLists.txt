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
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0/3.42.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderWebDAV CONFIG REQUIRED)
option(READER_CLOUD_BUILD_CONTENT_BOUND "Build the separate content-bound candidate package" OFF)
add_library(reader_cloud_import STATIC src/cloud_import.c)
target_include_directories(reader_cloud_import PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_cloud_import PUBLIC
  EXReader::exr_library EXReaderSideload::exr_sideload EXReaderWebDAV::exr_webdav)
set_target_properties(reader_cloud_import PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
set_property(TARGET reader_cloud_import PROPERTY INTERFACE_READER_CLOUD_IMPLEMENTATION legacy)
set_property(TARGET reader_cloud_import APPEND PROPERTY COMPATIBLE_INTERFACE_STRING READER_CLOUD_IMPLEMENTATION)
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
if(READER_CLOUD_BUILD_CONTENT_BOUND)
  find_package(EXReaderWebDAVObserved 0.1.0 CONFIG REQUIRED)
  add_library(reader_cloud_import_content_bound STATIC src/cloud_import.c)
  target_include_directories(reader_cloud_import_content_bound PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
  target_link_libraries(reader_cloud_import_content_bound PUBLIC
    EXReader::exr_library EXReaderSideload::exr_sideload EXReaderWebDAV::exr_webdav)
  target_compile_definitions(reader_cloud_import_content_bound PRIVATE READER_CLOUD_CONTENT_BOUND=1)
  set_target_properties(reader_cloud_import_content_bound PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
  set_property(TARGET reader_cloud_import_content_bound PROPERTY INTERFACE_READER_CLOUD_IMPLEMENTATION content_bound)
  set_property(TARGET reader_cloud_import_content_bound APPEND PROPERTY COMPATIBLE_INTERFACE_STRING READER_CLOUD_IMPLEMENTATION)
  if(MSVC)
    target_compile_options(reader_cloud_import_content_bound PRIVATE /W4 /WX)
    target_compile_definitions(reader_cloud_import_content_bound PRIVATE _CRT_SECURE_NO_WARNINGS)
  else()
    target_compile_options(reader_cloud_import_content_bound PRIVATE -Wall -Wextra -Werror)
  endif()
  install(TARGETS reader_cloud_import_content_bound EXPORT EXReaderCloudImportContentBoundTargets ARCHIVE DESTINATION lib)
  install(EXPORT EXReaderCloudImportContentBoundTargets NAMESPACE EXReaderCloudImportContentBound:: DESTINATION lib/cmake/EXReaderCloudImportContentBound)
  configure_package_config_file(EXReaderCloudImportContentBoundConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportContentBoundConfig.cmake"
    INSTALL_DESTINATION lib/cmake/EXReaderCloudImportContentBound)
  write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportContentBoundConfigVersion.cmake"
    VERSION 0.1.0 COMPATIBILITY SameMinorVersion)
  install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportContentBoundConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCloudImportContentBoundConfigVersion.cmake"
    DESTINATION lib/cmake/EXReaderCloudImportContentBound)
endif()
