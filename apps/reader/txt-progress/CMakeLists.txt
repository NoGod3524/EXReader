# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
option(EXR_READER_SELECTOR_BYTES_CANDIDATE "Explicit independent raw selector candidate; never default" OFF)
project(EXReaderTxtProgress VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
set(EXR_READER_FAMILY_VERSION 0.1.0)
set(EXR_REVISIONS_VERSION 0.3.0)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  set(EXR_READER_FAMILY_VERSION 0.2.0)
  set(EXR_REVISIONS_VERSION 0.4.0)
endif()
find_package(EXReaderRevisions ${EXR_REVISIONS_VERSION} EXACT CONFIG REQUIRED)
find_package(EXReaderReadingState ${EXR_READER_FAMILY_VERSION} EXACT CONFIG REQUIRED)
find_package(EXReaderReadingCommands ${EXR_READER_FAMILY_VERSION} EXACT CONFIG REQUIRED)
find_package(EXReaderCommands ${EXR_READER_FAMILY_VERSION} EXACT CONFIG REQUIRED)
add_library(reader_txt_progress STATIC src/txt_progress.cpp)
target_include_directories(reader_txt_progress PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_txt_progress PUBLIC
  EXReaderReadingState::reader_reading_state_codec
  EXReaderReadingCommands::reader_reading_commands
  EXReaderCommands::reader_commands
  EXReaderRevisions::reader_revisions)
if(MSVC)
  target_compile_options(reader_txt_progress PRIVATE /W4 /WX)
else()
  target_compile_options(reader_txt_progress PRIVATE -Wall -Wextra -Werror)
endif()
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  target_compile_definitions(reader_txt_progress PUBLIC EXR_READER_SELECTOR_BYTES_CANDIDATE=1)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_txt_progress EXPORT EXReaderTxtProgressTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_txt_progress.h DESTINATION include)
install(EXPORT EXReaderTxtProgressTargets NAMESPACE EXReaderTxtProgress:: DESTINATION lib/cmake/EXReaderTxtProgress)
configure_package_config_file(EXReaderTxtProgressConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderTxtProgressConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderTxtProgress)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderTxtProgressConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderTxtProgressConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderTxtProgressConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderTxtProgress)
