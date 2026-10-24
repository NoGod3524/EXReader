# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderLibraryHealth VERSION 1.0.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Optional package: the frozen public SDK library component and the one product
# metadata provider. No SDK private header, SQLite connection or catalog table
# is used here; only reader_catalog_page and exr_library_source are called.
if(EXR_SDK)
  find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS library
    PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
else()
  find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS library)
endif()
if(NOT TARGET EXReader::exr_library)
  message(FATAL_ERROR "The installed SDK does not provide the library component")
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)
add_library(reader_library_health STATIC src/library_health.c)
target_include_directories(reader_library_health PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_library_health PUBLIC EXReader::exr_library
  EXReaderProductCatalog::reader_catalog PRIVATE Threads::Threads)
if(MSVC)
  target_compile_options(reader_library_health PRIVATE /W4 /WX)
else()
  target_compile_options(reader_library_health PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_library_health EXPORT EXReaderLibraryHealthTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_library_health.h DESTINATION include)
install(EXPORT EXReaderLibraryHealthTargets NAMESPACE EXReaderLibraryHealth::
  DESTINATION lib/cmake/EXReaderLibraryHealth)
configure_package_config_file(EXReaderLibraryHealthConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLibraryHealthConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderLibraryHealth)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderLibraryHealthConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLibraryHealthConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLibraryHealthConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderLibraryHealth)
