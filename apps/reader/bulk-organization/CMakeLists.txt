# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderBulkOrganization VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Only the installed desktop metadata owner (and its installed dependencies).
find_package(EXReaderDesktopMetadata 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_bulk STATIC src/bulk.cpp)
target_include_directories(reader_bulk PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_bulk PUBLIC EXReaderDesktopMetadata::reader_desktop_metadata)
if(MSVC)
  target_compile_options(reader_bulk PRIVATE /W4 /WX)
else()
  target_compile_options(reader_bulk PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_bulk EXPORT EXReaderBulkOrganizationTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_bulk.h DESTINATION include)
install(EXPORT EXReaderBulkOrganizationTargets NAMESPACE EXReaderBulkOrganization:: DESTINATION lib/cmake/EXReaderBulkOrganization)
configure_package_config_file(EXReaderBulkOrganizationConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBulkOrganizationConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderBulkOrganization)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderBulkOrganizationConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBulkOrganizationConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBulkOrganizationConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderBulkOrganization)
