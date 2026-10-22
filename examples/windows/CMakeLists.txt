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
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_executable(EXReader WIN32 ../reader.c)
target_link_libraries(EXReader PRIVATE EXReader::exreader comdlg32 gdi32 shell32 user32)
if(NOT MSVC)
  target_link_libraries(EXReader PRIVATE m)
endif()
get_target_property(exr_type EXReader::exreader TYPE)
if(exr_type STREQUAL "SHARED_LIBRARY")
  find_file(EXR_RUNTIME NAMES exreader.dll libexreader.dll
            PATHS "${EXR_SDK}/bin" NO_DEFAULT_PATH REQUIRED)
  add_custom_command(TARGET EXReader POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different "${EXR_RUNTIME}" "$<TARGET_FILE_DIR:EXReader>"
    VERBATIM)
endif()
