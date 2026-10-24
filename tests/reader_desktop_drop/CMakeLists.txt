# SPDX-License-Identifier: MIT
# Acceptance project: builds only against the installed EXReaderDesktopDrop
# package plus the platform toolkit it was installed for.
cmake_minimum_required(VERSION 3.24)
project(DesktopDropAcceptance LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4)
else()
  add_compile_options(-Wall -Wextra)
endif()

if(WIN32)
  find_package(EXReaderDesktopDrop 0.1 CONFIG REQUIRED COMPONENTS win32)
  set(EXRDD_PLATFORM_TARGET EXReaderDesktopDrop::win32)
  set(EXRDD_PLATFORM_SOURCE probe_windows.c)
elseif(APPLE)
  enable_language(OBJC)
  find_package(EXReaderDesktopDrop 0.1 CONFIG REQUIRED COMPONENTS apple)
  set(EXRDD_PLATFORM_TARGET EXReaderDesktopDrop::apple)
  set(EXRDD_PLATFORM_SOURCE probe_apple.m)
else()
  find_package(EXReaderDesktopDrop 0.1 CONFIG REQUIRED COMPONENTS gtk)
  set(EXRDD_PLATFORM_TARGET EXReaderDesktopDrop::gtk)
  set(EXRDD_PLATFORM_SOURCE probe_gtk.c)
endif()

add_executable(drop-check check_drop.c)
target_link_libraries(drop-check PRIVATE EXReaderDesktopDrop::exr_desktop_drop)

add_executable(drop-consumer-cxx host_consumer.cpp)
target_link_libraries(drop-consumer-cxx PRIVATE EXReaderDesktopDrop::exr_desktop_drop)

add_executable(drop-probe ${EXRDD_PLATFORM_SOURCE})
target_link_libraries(drop-probe PRIVATE ${EXRDD_PLATFORM_TARGET})
if(APPLE)
  set_source_files_properties(probe_apple.m PROPERTIES COMPILE_OPTIONS "-fobjc-arc")
endif()

enable_testing()
add_test(NAME portable-parsers COMMAND drop-check)
