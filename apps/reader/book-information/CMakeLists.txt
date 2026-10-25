# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderBookInformation VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
# Only the installed public SDK and the installed product catalog package; no SDK
# private header, archive or second SQLite build is used here.
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed SDK: frozen 3.40.0 or explicit 3.41.0 candidate")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(40|41)\\.0$")
  message(FATAL_ERROR "Unsupported exact reader SDK version: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_book_information STATIC src/book_information.c)
target_include_directories(reader_book_information PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_book_information PUBLIC
  EXReader::exr_library EXReaderProductCatalog::reader_catalog)
if(MSVC)
  target_compile_options(reader_book_information PRIVATE /W4 /WX)
  target_compile_definitions(reader_book_information PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_book_information PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_book_information EXPORT EXReaderBookInformationTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_book_information.h DESTINATION include)
install(EXPORT EXReaderBookInformationTargets NAMESPACE EXReaderBookInformation:: DESTINATION lib/cmake/EXReaderBookInformation)
configure_package_config_file(EXReaderBookInformationConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBookInformationConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderBookInformation)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderBookInformationConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBookInformationConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderBookInformationConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderBookInformation)
