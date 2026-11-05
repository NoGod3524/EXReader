# SPDX-License-Identifier: MIT
# Independent optional Windows TTS component; the default reading build never adds it.
cmake_minimum_required(VERSION 3.22)
project(EXReaderTTSWindows VERSION 0.1.0 LANGUAGES C)
if(NOT WIN32)
  message(FATAL_ERROR "EXReaderTTSWindows is a Windows-only component (SAPI 5)")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(public_headers include/reader_tts.h include/reader_tts_windows.h)
add_library(reader_tts STATIC src/reader_tts.c src/sapi_worker.c)
add_library(EXReaderTTSWindows::reader_tts ALIAS reader_tts)
target_include_directories(reader_tts PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
# SAPI 5 (sapi.dll import library) and the COM runtime.
target_link_libraries(reader_tts PRIVATE sapi ole32 uuid)
if(MSVC)
  target_compile_options(reader_tts PRIVATE /W4 /WX)
else()
  target_compile_options(reader_tts PRIVATE -Wall -Wextra -Werror)
endif()
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
install(TARGETS reader_tts EXPORT EXReaderTTSWindowsTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(FILES ${public_headers} DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ../../LICENSE DESTINATION ${CMAKE_INSTALL_DATADIR}/exreader-tts-windows RENAME LICENSE.txt)
install(EXPORT EXReaderTTSWindowsTargets NAMESPACE EXReaderTTSWindows:: DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSWindows)
configure_package_config_file(EXReaderTTSWindowsConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSWindowsConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSWindows)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSWindowsConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSWindowsConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSWindowsConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSWindows)
