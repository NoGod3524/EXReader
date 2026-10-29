# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
option(EXR_READER_SELECTOR_BYTES_CANDIDATE "Explicit independent raw selector candidate; never default" OFF)
option(EXR_READER_PURE_CAPTURE_CANDIDATE "Explicit public pure raw capture capability; never default" OFF)
if(EXR_READER_PURE_CAPTURE_CANDIDATE AND NOT EXR_READER_SELECTOR_BYTES_CANDIDATE)
  message(FATAL_ERROR "Pure raw capture requires the explicit raw reading-state family")
endif()
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  project(EXReaderReadingState VERSION 0.2.0 LANGUAGES C CXX)
else()
  project(EXReaderReadingState VERSION 0.1.0 LANGUAGES C CXX)
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# The frozen installed SDK and the installed revision/product packages only;
# no SDK private header, archive or second SQLite build is used here.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0/3.42.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
set(EXR_REVISIONS_VERSION 0.3.0)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  set(EXR_REVISIONS_VERSION 0.4.0)
endif()
find_package(EXReaderRevisions ${EXR_REVISIONS_VERSION} EXACT CONFIG REQUIRED)
add_library(reader_reading_state_codec STATIC src/reading_state.cpp)
add_library(reader_reading_state STATIC src/reading_resolve.cpp)
# Codec copies public selector values; it never calls or links the SDK. Its
# installed consumer can coexist with a separately owned SDK/SQLite library.
target_include_directories(reader_reading_state_codec PUBLIC
  $<TARGET_PROPERTY:EXReader::exr_core,INTERFACE_INCLUDE_DIRECTORIES>)
target_link_libraries(reader_reading_state_codec PUBLIC EXReaderRevisions::reader_revisions
  PRIVATE EXReaderProductCatalog::reader_catalog_sqlite)
target_link_libraries(reader_reading_state PUBLIC reader_reading_state_codec
  EXReader::exr_library EXReader::exr_core)
foreach(target reader_reading_state reader_reading_state_codec)
  target_include_directories(${target} PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /WX)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
  endif()
endforeach()
include(CMakePackageConfigHelpers)
install(TARGETS reader_reading_state reader_reading_state_codec EXPORT EXReaderReadingStateTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_reading_state.h DESTINATION include)
install(EXPORT EXReaderReadingStateTargets NAMESPACE EXReaderReadingState:: DESTINATION lib/cmake/EXReaderReadingState)
if(EXR_READER_PURE_CAPTURE_CANDIDATE)
  target_compile_definitions(reader_reading_state_codec PUBLIC EXR_READER_PURE_CAPTURE_CANDIDATE=1)
  install(FILES include/reader_reading_state_capture_raw_candidate.h DESTINATION include)
endif()
configure_package_config_file(EXReaderReadingStateConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderReadingState)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfigVersion.cmake" DESTINATION lib/cmake/EXReaderReadingState)

if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  target_compile_definitions(reader_reading_state_codec PUBLIC EXR_READER_SELECTOR_BYTES_CANDIDATE=1 EXR_READER_PUBLIC_RETAINED_RAW_V1=1)
  install(FILES include/reader_reading_state_retained_raw_v1.h DESTINATION include)
endif()

# RAW-CANDIDATE ORIGIN GUARD: append-only; never changes imported targets.
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  _exr_raw_guard_target(EXReaderRevisions::reader_revisions "${EXReaderRevisions_DIR}"
    reader_revisions.h READER_REVISIONS_VERSION 0.4.0 TRUE)
  foreach(_sdk_target EXReader::exr_core EXReader::exr_library)
    _exr_raw_guard_target("${_sdk_target}" "${EXReader_DIR}" exr/base.h EXR_VERSION "${EXR_SDK_VERSION}" FALSE)
  endforeach()
  if(TARGET EXReader::exreader)
    _exr_raw_guard_target(EXReader::exreader "${EXReader_DIR}" exr/base.h EXR_VERSION "${EXR_SDK_VERSION}" FALSE)
  endif()
endif()

if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  _exr_public_boundary_guard(EXReaderRevisions::reader_revisions "${EXReaderRevisions_DIR}"
    reader_selector_bytes_v1.h READER_REV_SELECTOR_BYTES_API_VERSION EXR_READER_PUBLIC_SELECTOR_BYTES_V1)
endif()
