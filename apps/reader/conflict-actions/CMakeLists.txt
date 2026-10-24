# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderConflictActions VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderCommands 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_conflict_actions STATIC src/conflict_actions.cpp)
target_include_directories(reader_conflict_actions PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_conflict_actions PUBLIC EXReaderCommands::reader_commands)
if(MSVC)
  target_compile_options(reader_conflict_actions PRIVATE /W4 /WX)
else()
  target_compile_options(reader_conflict_actions PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_conflict_actions EXPORT EXReaderConflictActionsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_conflict_actions.h DESTINATION include)
install(EXPORT EXReaderConflictActionsTargets NAMESPACE EXReaderConflictActions:: DESTINATION lib/cmake/EXReaderConflictActions)
configure_package_config_file(EXReaderConflictActionsConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderConflictActionsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderConflictActions)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderConflictActionsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderConflictActionsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderConflictActionsConfigVersion.cmake" DESTINATION lib/cmake/EXReaderConflictActions)
