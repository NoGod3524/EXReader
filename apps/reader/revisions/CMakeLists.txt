# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
option(EXR_READER_SELECTOR_BYTES_CANDIDATE "Explicit independent raw selector candidate; never default" OFF)
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  project(EXReaderRevisions VERSION 0.4.0 LANGUAGES C CXX)
else()
  project(EXReaderRevisions VERSION 0.3.0 LANGUAGES C CXX)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED
  PATHS "${READER_PRODUCT_PREFIX}" NO_DEFAULT_PATH)
# Reuse the existing OPDS public SHA-256 implementation; no second JSON parser
# or crypto dependency. This private static implementation target is installed
# only to satisfy the module's static link, not exposed in its public header.
add_library(reader_revision_hash STATIC ../../../extras/opds/src/opds_core.c)
target_include_directories(reader_revision_hash PRIVATE ../../../extras/opds/include ../../../extras/opds/src)
add_library(reader_revisions STATIC src/revisions.cpp)
target_include_directories(reader_revisions PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include> PRIVATE ../../../extras/opds/include)
target_link_libraries(reader_revisions PRIVATE EXReaderProductCatalog::reader_catalog
  EXReaderProductCatalog::reader_catalog_sqlite reader_revision_hash)
if(WIN32)
  target_link_libraries(reader_revisions PRIVATE bcrypt)
endif()
if(MSVC)
  target_compile_options(reader_revisions PRIVATE /W4 /WX)
  target_compile_definitions(reader_revisions PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_revisions PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_revisions reader_revision_hash EXPORT EXReaderRevisionsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_revisions.h include/reader_projection.h DESTINATION include)
install(EXPORT EXReaderRevisionsTargets NAMESPACE EXReaderRevisions:: DESTINATION lib/cmake/EXReaderRevisions)
configure_package_config_file(EXReaderRevisionsConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderRevisionsConfig.cmake" INSTALL_DESTINATION lib/cmake/EXReaderRevisions)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderRevisionsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderRevisionsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderRevisionsConfigVersion.cmake" DESTINATION lib/cmake/EXReaderRevisions)

if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  target_compile_definitions(reader_revisions PUBLIC EXR_READER_SELECTOR_BYTES_CANDIDATE=1)
endif()
if(EXR_READER_SELECTOR_BYTES_CANDIDATE)
  install(FILES include/reader_selector_bytes_detail.h DESTINATION include)
endif()
