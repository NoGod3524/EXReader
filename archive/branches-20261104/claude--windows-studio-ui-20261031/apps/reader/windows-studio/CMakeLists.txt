# SPDX-License-Identifier: MIT
# EXReader Studio: standalone Windows client built against an installed SDK.
#   cmake -S apps/reader/windows-studio -B build/studio -G Ninja -DEXR_SDK=<sdk prefix>
cmake_minimum_required(VERSION 3.24)
project(EXReaderStudio LANGUAGES C CXX RC)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT WIN32)
  message(FATAL_ERROR "EXReader Studio is a Windows client")
endif()
find_package(EXReader CONFIG REQUIRED COMPONENTS core library PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_executable(exreader-studio WIN32 src/ui.cpp src/engine.cpp res/studio.rc)
target_compile_definitions(exreader-studio PRIVATE UNICODE _UNICODE NOMINMAX WIN32_LEAN_AND_MEAN _WIN32_WINNT=0x0A00 WINVER=0x0A00)
target_link_libraries(exreader-studio PRIVATE EXReader::exr_library EXReader::exr_core EXReader::exr_pdf
  d2d1 dwrite dwmapi windowscodecs comctl32 comdlg32 shell32 ole32 oleaut32 uuid uiautomationcore)
if(MSVC)
  target_compile_options(exreader-studio PRIVATE $<$<COMPILE_LANGUAGE:CXX>:/W4 /utf-8>)
  target_compile_definitions(exreader-studio PRIVATE _CRT_SECURE_NO_WARNINGS)
  # res/studio.rc embeds the manifest; the linker must not add a second one.
  target_link_options(exreader-studio PRIVATE /MANIFEST:NO)
  set_property(TARGET exreader-studio PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
else()
  target_compile_options(exreader-studio PRIVATE
    $<$<COMPILE_LANGUAGE:CXX>:-Wall -Wextra -Wno-missing-field-initializers -finput-charset=UTF-8 -fexec-charset=UTF-8>)
  target_link_options(exreader-studio PRIVATE -municode -static)
endif()
install(TARGETS exreader-studio RUNTIME DESTINATION bin)
