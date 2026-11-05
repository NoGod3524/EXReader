# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderReadingState VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# The frozen installed SDK and the installed revision/product packages only;
# no SDK private header, archive or second SQLite build is used here.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
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
configure_package_config_file(EXReaderReadingStateConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderReadingState)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingStateConfigVersion.cmake" DESTINATION lib/cmake/EXReaderReadingState)
