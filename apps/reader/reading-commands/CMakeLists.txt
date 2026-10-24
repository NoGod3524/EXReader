# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderReadingCommands VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_reading_commands STATIC src/reading_commands.cpp)
target_include_directories(reader_reading_commands PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_reading_commands PUBLIC EXReaderReadingState::reader_reading_state_codec)
if(MSVC)
  target_compile_options(reader_reading_commands PRIVATE /W4 /WX)
else()
  target_compile_options(reader_reading_commands PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_reading_commands EXPORT EXReaderReadingCommandsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_reading_commands.h DESTINATION include)
install(EXPORT EXReaderReadingCommandsTargets NAMESPACE EXReaderReadingCommands:: DESTINATION lib/cmake/EXReaderReadingCommands)
configure_package_config_file(EXReaderReadingCommandsConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingCommandsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderReadingCommands)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingCommandsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingCommandsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderReadingCommandsConfigVersion.cmake" DESTINATION lib/cmake/EXReaderReadingCommands)
