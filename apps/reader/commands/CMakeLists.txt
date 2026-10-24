# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderCommands VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
add_library(reader_commands STATIC src/commands.cpp)
target_include_directories(reader_commands PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_commands PUBLIC EXReaderRevisions::reader_revisions)
if(MSVC)
  target_compile_options(reader_commands PRIVATE /W4 /WX)
else()
  target_compile_options(reader_commands PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_commands EXPORT EXReaderCommandsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_commands.h DESTINATION include)
install(EXPORT EXReaderCommandsTargets NAMESPACE EXReaderCommands:: DESTINATION lib/cmake/EXReaderCommands)
configure_package_config_file(EXReaderCommandsConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCommandsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderCommands)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderCommandsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCommandsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderCommandsConfigVersion.cmake" DESTINATION lib/cmake/EXReaderCommands)
