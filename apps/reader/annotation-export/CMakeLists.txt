# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderAnnotationExport VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Optional package built only against installed packages: the unchanged product
# revision store and reading-state decoder (which bring the frozen SDK). No
# SDK private header, SQL or second SQLite is used. Put the installed revision,
# product, reading-state and SDK prefixes on CMAKE_PREFIX_PATH.
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_annotation_export STATIC src/annotation_export.cpp)
target_include_directories(reader_annotation_export PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_annotation_export PUBLIC EXReaderReadingState::reader_reading_state
  EXReaderRevisions::reader_revisions)
if(MSVC)
  target_compile_options(reader_annotation_export PRIVATE /W4 /WX)
  target_compile_definitions(reader_annotation_export PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_annotation_export PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_annotation_export EXPORT EXReaderAnnotationExportTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_annotation_export.h DESTINATION include)
install(EXPORT EXReaderAnnotationExportTargets NAMESPACE EXReaderAnnotationExport:: DESTINATION lib/cmake/EXReaderAnnotationExport)
configure_package_config_file(EXReaderAnnotationExportConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationExportConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderAnnotationExport)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationExportConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationExportConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationExportConfigVersion.cmake" DESTINATION lib/cmake/EXReaderAnnotationExport)
