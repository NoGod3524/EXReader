# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderDiagnosticReport VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# Optional reader module: one static C ABI library, no dependency on the core
# SDK, no database, no network, no WebView. Hosts add it explicitly; the
# default reading configuration never pulls it in.
add_library(reader_diagnostic_report STATIC src/report.c src/io.c)
target_include_directories(reader_diagnostic_report PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(MSVC)
  target_compile_options(reader_diagnostic_report PRIVATE /W4 /WX)
else()
  target_compile_options(reader_diagnostic_report PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_diagnostic_report EXPORT EXReaderDiagnosticReportTargets
  ARCHIVE DESTINATION lib)
install(FILES include/reader_diagnostic_report.h DESTINATION include)
install(EXPORT EXReaderDiagnosticReportTargets NAMESPACE EXReaderDiagnosticReport::
  DESTINATION lib/cmake/EXReaderDiagnosticReport)
configure_package_config_file(EXReaderDiagnosticReportConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDiagnosticReportConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderDiagnosticReport)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDiagnosticReportConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDiagnosticReportConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDiagnosticReportConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderDiagnosticReport)
