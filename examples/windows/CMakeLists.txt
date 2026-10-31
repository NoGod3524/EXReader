# SPDX-License-Identifier: MIT
# Independent consumer build for the Windows reference host.
#
# examples/CMakeLists.txt is owned by the integration branch, so this project
# consumes the installed SDK directly and reuses ../reader.c without touching
# the shared example entry point. It also works from the installed tree
# (stage/examples/windows).
cmake_minimum_required(VERSION 3.24)
project(EXReaderWindowsHost LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(NOT EXR_SDK)
  message(FATAL_ERROR "Set -DEXR_SDK=<installed SDK prefix>")
endif()
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
set(EXR_SDK_VERSION "3.42.0" CACHE STRING "Exact installed Windows reading SDK: 3.41.0 or frozen 3.42.0")
if(NOT EXR_SDK_VERSION MATCHES "^3\\.(41|42)\\.0$")
  message(FATAL_ERROR "Unsupported exact Windows reader SDK: ${EXR_SDK_VERSION}")
endif()
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
set(READER_C02_PREFIX "" CACHE PATH "Installed C02 native admission, CAS and hardening provider")
if(NOT IS_ABSOLUTE "${READER_C02_PREFIX}")
  message(FATAL_ERROR "Every Windows library host requires an absolute READER_C02_PREFIX")
endif()
file(TO_CMAKE_PATH "${READER_C02_PREFIX}" READER_C02_PREFIX)
add_library(reader_c02 INTERFACE)
target_include_directories(reader_c02 INTERFACE
  "${READER_C02_PREFIX}/include/exreader-coordinator-native"
  "${READER_C02_PREFIX}/include/exreader-coordinator-cas"
  "${READER_C02_PREFIX}/include/exreader-migration-coordinator-hardening")
target_link_libraries(reader_c02 INTERFACE
  "${READER_C02_PREFIX}/lib/exreader-coordinator-native.lib"
  "${READER_C02_PREFIX}/lib/exreader-coordinator-cas.lib"
  "${READER_C02_PREFIX}/lib/exreader-migration-coordinator-hardening.lib" advapi32)
if(TARGET EXReader::exreader)
  set(reader_sdk EXReader::exreader)
else()
  set(reader_sdk EXReader::exr_library EXReader::exr_core)
endif()
add_executable(EXReader WIN32 ../reader.c)
target_link_libraries(EXReader PRIVATE reader_c02 ${reader_sdk} comdlg32 gdi32 shell32 user32)
if(NOT MSVC)
  target_link_libraries(EXReader PRIVATE m)
endif()
set(exr_type "")
if(TARGET EXReader::exreader)
  get_target_property(exr_type EXReader::exreader TYPE)
endif()
if(exr_type STREQUAL "SHARED_LIBRARY")
  find_file(EXR_RUNTIME NAMES exreader.dll libexreader.dll
            PATHS "${EXR_SDK}/bin" NO_DEFAULT_PATH REQUIRED)
  add_custom_command(TARGET EXReader POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${EXR_RUNTIME}" "$<TARGET_FILE_DIR:EXReader>"
    VERBATIM)
endif()
