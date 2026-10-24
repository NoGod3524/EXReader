# SPDX-License-Identifier: MIT
# Two build modes of the same test source directory:
#   -DEXR_TTS_APPLE_LOGIC=ON   platform-neutral logic suite (module source + fake engine)
#   (default)                  installed-package consumer probe (real AVFoundation backend)
cmake_minimum_required(VERSION 3.24)
project(EXReaderTTSAppleProbe LANGUAGES C CXX OBJCXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OBJCXX_STANDARD 17)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)

option(EXR_TTS_APPLE_LOGIC "Build the platform-neutral logic suite from the module source" OFF)
set(EXR_TTS_APPLE_MODULE_DIR "" CACHE PATH "extras/reader-tts-apple source directory")

if(EXR_TTS_APPLE_LOGIC)
  if(NOT EXR_TTS_APPLE_MODULE_DIR)
    message(FATAL_ERROR "EXR_TTS_APPLE_MODULE_DIR is required when EXR_TTS_APPLE_LOGIC is on")
  endif()
  add_library(reader_tts_test STATIC
    ${EXR_TTS_APPLE_MODULE_DIR}/src/core.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/fake_engine.cpp)
  target_include_directories(reader_tts_test PUBLIC
    ${EXR_TTS_APPLE_MODULE_DIR}/include
    ${EXR_TTS_APPLE_MODULE_DIR}/src
    ${CMAKE_CURRENT_SOURCE_DIR})
  target_compile_definitions(reader_tts_test PUBLIC READER_TTS_TESTING)
  target_compile_options(reader_tts_test PRIVATE -Wall -Wextra -Werror)
  add_executable(reader-tts-logic logic_suite.cpp)
  target_link_libraries(reader-tts-logic PRIVATE reader_tts_test)
  target_compile_options(reader-tts-logic PRIVATE -Wall -Wextra -Werror)
  find_package(Threads REQUIRED)
  target_link_libraries(reader-tts-logic PRIVATE Threads::Threads)
else()
  find_package(EXReaderTTSApple 0.1.0 CONFIG REQUIRED)
  find_library(EXR_TTS_UIKIT UIKit)
  find_library(EXR_TTS_AVFOUNDATION AVFoundation REQUIRED)
  if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
    add_executable(ReaderTTSProbe MACOSX_BUNDLE ios_main.mm probe.mm)
    set_target_properties(ReaderTTSProbe PROPERTIES
      MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/Info.plist")
    target_link_libraries(ReaderTTSProbe PRIVATE ${EXR_TTS_UIKIT})
  else()
    add_executable(ReaderTTSProbe probe.mm)
  endif()
  target_compile_options(ReaderTTSProbe PRIVATE -Wall -Wextra -Werror -fobjc-arc)
  target_link_libraries(ReaderTTSProbe PRIVATE
    EXReaderTTSApple::reader_tts
    ${EXR_TTS_AVFOUNDATION})
endif()
