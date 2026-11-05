# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderTTSAndroid VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
if(CMAKE_SYSTEM_NAME STREQUAL "Android")
  set(_android_default ON)
else()
  set(_android_default OFF)
endif()
option(EXR_TTS_ANDROID_ALLOW_FOREIGN_TARGET "Compile the Android backend for a host-only syntax check" OFF)
if(NOT CMAKE_SYSTEM_NAME STREQUAL "Android" AND NOT EXR_TTS_ANDROID_ALLOW_FOREIGN_TARGET)
  message(FATAL_ERROR "The Android TextToSpeech backend builds only for Android targets")
endif()
if(DEFINED ANDROID_PLATFORM_LEVEL AND ANDROID_PLATFORM_LEVEL LESS 26)
  message(FATAL_ERROR "Android TextToSpeech requires API 26 or newer")
endif()
add_library(reader_tts STATIC src/reader_tts_android.c)
add_library(EXReaderTTSAndroid::reader_tts ALIAS reader_tts)
target_include_directories(reader_tts PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
set_target_properties(reader_tts PROPERTIES POSITION_INDEPENDENT_CODE ON)
if(NOT MSVC)
  target_compile_options(reader_tts PRIVATE -Wall -Wextra -Werror)
endif()
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
install(TARGETS reader_tts EXPORT EXReaderTTSAndroidTargets ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(FILES include/reader_tts.h include/reader_tts_android.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ../../LICENSE DESTINATION ${CMAKE_INSTALL_DATADIR}/exreader-tts-android RENAME LICENSE.txt)
install(EXPORT EXReaderTTSAndroidTargets NAMESPACE EXReaderTTSAndroid::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSAndroid)
configure_package_config_file(EXReaderTTSAndroidConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAndroidConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSAndroid)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAndroidConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAndroidConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSAndroidConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSAndroid)
