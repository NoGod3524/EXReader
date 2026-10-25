# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
option(EXR_READER_SELECTOR_BYTES_CANDIDATE "Explicit independent raw selector candidate; never default" OFF)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  project(EXReaderJumpHistory VERSION 0.2.0 LANGUAGES C CXX)
else()
  project(EXReaderJumpHistory VERSION 0.1.0 LANGUAGES C CXX)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Only the installed reading-state adapter, and through it the installed exact
# SDK (frozen 3.40.0 or approved 3.41.0) and the unchanged revision module. No
# SDK private header or archive, no second SQLite build, no product schema
# change, no new database. The default install is EXReaderReadingState 0.1.0; the
# explicit raw candidate install is EXReaderReadingState 0.2.0 and is installed
# as EXReaderJumpHistory 0.2.0, so the two installed families never share a
# version.
set(EXR_READING_STATE_VERSION 0.1.0)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  set(EXR_READING_STATE_VERSION 0.2.0)
endif()
find_package(EXReaderReadingState ${EXR_READING_STATE_VERSION} EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
# The exact version file is not the only family guard: the exact imported target
# also has to carry the capability this package was configured for. A default
# build refuses a raw candidate adapter target and a raw candidate build refuses
# a legacy adapter target, so a mixed install cannot link and silently change
# which entry points exist.
get_target_property(_jh_adapter_definitions EXReaderReadingState::reader_reading_state_codec INTERFACE_COMPILE_DEFINITIONS)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  if(NOT "EXR_READER_SELECTOR_BYTES_CANDIDATE=1" IN_LIST _jh_adapter_definitions)
    message(FATAL_ERROR "Raw candidate jump history requires the raw candidate reading-state target")
  endif()
else()
  if("EXR_READER_SELECTOR_BYTES_CANDIDATE=1" IN_LIST _jh_adapter_definitions)
    message(FATAL_ERROR "Default jump history cannot consume a raw candidate reading-state target")
  endif()
endif()
add_library(reader_jump_history STATIC src/jump_history.cpp)
target_include_directories(reader_jump_history PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_jump_history PUBLIC EXReaderReadingState::reader_reading_state Threads::Threads)
if(MSVC)
  target_compile_options(reader_jump_history PRIVATE /W4 /WX)
else()
  target_compile_options(reader_jump_history PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_jump_history EXPORT EXReaderJumpHistoryTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_jump_history.h DESTINATION include)
install(EXPORT EXReaderJumpHistoryTargets NAMESPACE EXReaderJumpHistory:: DESTINATION lib/cmake/EXReaderJumpHistory)
configure_package_config_file(EXReaderJumpHistoryConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderJumpHistoryConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderJumpHistory)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderJumpHistoryConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderJumpHistoryConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderJumpHistoryConfigVersion.cmake" DESTINATION lib/cmake/EXReaderJumpHistory)

if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  target_compile_definitions(reader_jump_history PUBLIC EXR_READER_SELECTOR_BYTES_CANDIDATE=1)
endif()
