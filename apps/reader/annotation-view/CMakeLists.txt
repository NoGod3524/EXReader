# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderAnnotationView VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Optional package over the installed, unchanged revision and reading-state
# packages. The codec target carries no SDK runtime; a mobile host keeps its
# existing SDK owner. No SDK private header, SQL or second SQLite is used here.
find_package(EXReaderReadingState 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_annotation_view STATIC src/annotation_view.cpp)
target_include_directories(reader_annotation_view PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_annotation_view PUBLIC EXReaderReadingState::reader_reading_state_codec)
if(MSVC)
  target_compile_options(reader_annotation_view PRIVATE /W4 /WX)
else()
  target_compile_options(reader_annotation_view PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_annotation_view EXPORT EXReaderAnnotationViewTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_annotation_view.h DESTINATION include)
install(EXPORT EXReaderAnnotationViewTargets NAMESPACE EXReaderAnnotationView:: DESTINATION lib/cmake/EXReaderAnnotationView)
configure_package_config_file(EXReaderAnnotationViewConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationViewConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderAnnotationView)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationViewConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationViewConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAnnotationViewConfigVersion.cmake" DESTINATION lib/cmake/EXReaderAnnotationView)
