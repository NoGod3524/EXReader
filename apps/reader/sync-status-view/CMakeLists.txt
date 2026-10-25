# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderSyncView VERSION 0.1.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_sync_view STATIC src/sync_view.cpp)
target_include_directories(reader_sync_view PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_sync_view PUBLIC EXReaderSession::reader_session)
if(MSVC)
  target_compile_options(reader_sync_view PRIVATE /W4 /WX)
else()
  target_compile_options(reader_sync_view PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_sync_view EXPORT EXReaderSyncViewTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_sync_view.h DESTINATION include)
install(EXPORT EXReaderSyncViewTargets NAMESPACE EXReaderSyncView:: DESTINATION lib/cmake/EXReaderSyncView)
configure_package_config_file(EXReaderSyncViewConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSyncViewConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderSyncView)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderSyncViewConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSyncViewConfig.cmake" "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSyncViewConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderSyncView)
