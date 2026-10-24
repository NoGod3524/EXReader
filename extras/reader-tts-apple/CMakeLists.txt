# SPDX-License-Identifier: MIT
# Independent optional Apple speech module. The default reading-core/library
# build never adds it, no host target links it by accident, and nothing here
# depends on another work package.
cmake_minimum_required(VERSION 3.22)
project(EXReaderTTSApple VERSION 0.1.0 LANGUAGES C CXX OBJCXX)

if(NOT APPLE)
  message(FATAL_ERROR "EXReaderTTSApple provides native macOS/iOS speech and builds only on Apple platforms")
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OBJCXX_STANDARD 17)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)

add_library(reader_tts STATIC src/core.cpp src/apple_engine.mm)
add_library(EXReaderTTSApple::reader_tts ALIAS reader_tts)
target_include_directories(reader_tts PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_options(reader_tts PRIVATE
  -Wall -Wextra -Werror
  $<$<COMPILE_LANGUAGE:OBJCXX>:-fobjc-arc>)
find_library(EXR_TTS_APPLE_AVFOUNDATION AVFoundation REQUIRED)
find_library(EXR_TTS_APPLE_FOUNDATION Foundation REQUIRED)
target_link_libraries(reader_tts PRIVATE
  $<BUILD_INTERFACE:${EXR_TTS_APPLE_AVFOUNDATION}>
  $<BUILD_INTERFACE:${EXR_TTS_APPLE_FOUNDATION}>)
set_target_properties(reader_tts PROPERTIES POSITION_INDEPENDENT_CODE ON)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
install(TARGETS reader_tts EXPORT EXReaderTTSAppleTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES include/reader_tts.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../../LICENSE
  DESTINATION ${CMAKE_INSTALL_DATADIR}/exreader-tts-apple RENAME LICENSE.txt)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../../docs/READER-TTS-APPLE.md
  DESTINATION ${CMAKE_INSTALL_DATADIR}/exreader-tts-apple)
install(EXPORT EXReaderTTSAppleTargets NAMESPACE EXReaderTTSApple::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSApple)
configure_package_config_file(EXReaderTTSAppleConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAppleConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSApple)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAppleConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAppleConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAppleConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSApple)
