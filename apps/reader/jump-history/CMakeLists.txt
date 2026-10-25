# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderJumpHistory VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Only the installed reading-state adapter, and through it the frozen 3.40.0 SDK
# and the unchanged revision module. No SDK private header or archive, no second
# SQLite build, no product schema change, no new database.
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
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
