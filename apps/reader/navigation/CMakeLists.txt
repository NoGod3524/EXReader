# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderNavigation VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Optional package: only the installed frozen SDK core component. No product
# catalog, revision store, SQLite or SDK private header is used here.
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
find_package(Threads REQUIRED)
add_library(reader_navigation STATIC src/navigation.cpp)
target_include_directories(reader_navigation PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_navigation PUBLIC EXReader::exr_core PRIVATE Threads::Threads)
if(MSVC)
  target_compile_options(reader_navigation PRIVATE /W4 /WX)
else()
  target_compile_options(reader_navigation PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_navigation EXPORT EXReaderNavigationTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_navigation.h DESTINATION include)
install(EXPORT EXReaderNavigationTargets NAMESPACE EXReaderNavigation:: DESTINATION lib/cmake/EXReaderNavigation)
configure_package_config_file(EXReaderNavigationConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderNavigationConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderNavigation)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderNavigationConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderNavigationConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderNavigationConfigVersion.cmake" DESTINATION lib/cmake/EXReaderNavigation)
