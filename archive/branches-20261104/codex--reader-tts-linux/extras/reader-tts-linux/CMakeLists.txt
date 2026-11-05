# SPDX-License-Identifier: MIT
# Independent optional module; the default reading-core/library build never adds
# it and no host target links it yet. System dependency: libspeechd only.
cmake_minimum_required(VERSION 3.22)
project(EXReaderTTSLinux VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

option(READER_TTS_BUILD_TEST_HOOKS "Build the fault-injection hooks used by the test suite" OFF)

find_package(Threads REQUIRED)

# Locate the system Speech Dispatcher development files: pkg-config first, then a
# plain header/library lookup so the module also builds where no .pc is shipped.
find_package(PkgConfig QUIET)
if(PkgConfig_FOUND)
  pkg_check_modules(SPEECHD QUIET speech-dispatcher-2.1)
  if(NOT SPEECHD_FOUND)
    pkg_check_modules(SPEECHD QUIET speech-dispatcher)
  endif()
endif()
if(SPEECHD_FOUND)
  set(EXREADER_TTS_SPEECHD_INCLUDE_DIRS ${SPEECHD_INCLUDE_DIRS})
  message(STATUS "reader-tts-linux: libspeechd ${SPEECHD_VERSION} via pkg-config")
else()
  find_path(EXREADER_TTS_SPEECHD_INCLUDE_DIR NAMES libspeechd.h PATH_SUFFIXES speech-dispatcher REQUIRED)
  find_library(EXREADER_TTS_SPEECHD_LIBRARY NAMES speechd REQUIRED)
  set(EXREADER_TTS_SPEECHD_INCLUDE_DIRS ${EXREADER_TTS_SPEECHD_INCLUDE_DIR})
  message(STATUS "reader-tts-linux: libspeechd via find_path/find_library (${EXREADER_TTS_SPEECHD_LIBRARY})")
endif()

# Consumers link the system library by name; no private libspeechd header is part
# of this public interface.
add_library(EXReaderTTSLinux_speechd INTERFACE)
target_link_libraries(EXReaderTTSLinux_speechd INTERFACE speechd)
add_library(EXReaderTTSLinux::speechd ALIAS EXReaderTTSLinux_speechd)

add_library(reader_tts STATIC src/reader_tts_linux.c)
add_library(EXReaderTTSLinux::reader_tts ALIAS reader_tts)
target_include_directories(reader_tts
  PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>
  PRIVATE ${EXREADER_TTS_SPEECHD_INCLUDE_DIRS})
target_link_libraries(reader_tts PUBLIC Threads::Threads EXReaderTTSLinux_speechd)
if(READER_TTS_BUILD_TEST_HOOKS)
  target_compile_definitions(reader_tts PRIVATE READER_TTS_TEST_HOOKS)
endif()
if(MSVC)
  target_compile_options(reader_tts PRIVATE /W4 /WX)
else()
  target_compile_options(reader_tts PRIVATE -Wall -Wextra -Werror)
endif()

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
install(TARGETS reader_tts EXReaderTTSLinux_speechd EXPORT EXReaderTTSLinuxTargets
  ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
  INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES include/reader_tts.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
if(READER_TTS_BUILD_TEST_HOOKS)
  install(FILES include/reader_tts_test.h DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
endif()
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/../../LICENSE
  DESTINATION ${CMAKE_INSTALL_DATADIR}/exreader-tts-linux RENAME LICENSE.txt)
install(EXPORT EXReaderTTSLinuxTargets NAMESPACE EXReaderTTSLinux::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSLinux)
configure_package_config_file(EXReaderTTSLinuxConfig.cmake.in
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSLinuxConfig.cmake
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSLinux)
write_basic_package_version_file(${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSLinuxConfigVersion.cmake
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSLinuxConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/EXReaderTTSLinuxConfigVersion.cmake
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/EXReaderTTSLinux)
