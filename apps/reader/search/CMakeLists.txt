# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderSearch VERSION 0.1.0 LANGUAGES C CXX)
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
add_library(reader_search STATIC src/search.cpp)
target_include_directories(reader_search PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_search PUBLIC EXReader::exr_core PRIVATE Threads::Threads)
if(MSVC)
  target_compile_options(reader_search PRIVATE /W4 /WX)
else()
  target_compile_options(reader_search PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_search EXPORT EXReaderSearchTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_search.h DESTINATION include)
install(EXPORT EXReaderSearchTargets NAMESPACE EXReaderSearch:: DESTINATION lib/cmake/EXReaderSearch)
configure_package_config_file(EXReaderSearchConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSearchConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderSearch)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderSearchConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSearchConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSearchConfigVersion.cmake" DESTINATION lib/cmake/EXReaderSearch)
