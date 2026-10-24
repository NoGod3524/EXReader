# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderDesktopDrop VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
if(MSVC)
  if(NOT CMAKE_MSVC_RUNTIME_LIBRARY)
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  endif()
  add_compile_options(/utf-8)
endif()
option(EXR_DESKTOP_DROP_GTK "Build the GTK3 drop/clipboard adapter on Unix" ON)
option(EXR_DESKTOP_DROP_TEST_HOOKS "Build the acceptance-only lifecycle counters" OFF)

add_library(exr_desktop_drop STATIC src/core.c)
target_include_directories(exr_desktop_drop PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>
  PRIVATE src)
set_target_properties(exr_desktop_drop PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON OUTPUT_NAME exr_desktop_drop
  EXPORT_NAME exr_desktop_drop)
add_library(EXReaderDesktopDrop::exr_desktop_drop ALIAS exr_desktop_drop)
if(WIN32)
  target_link_libraries(exr_desktop_drop PUBLIC user32)
endif()

set(exrdd_targets exr_desktop_drop)
set(exrdd_headers include/exr_desktop_drop.h)
set(exrdd_components "")

if(WIN32)
  add_library(exr_desktop_drop_win32 STATIC src/windows.c)
  target_link_libraries(exr_desktop_drop_win32 PUBLIC exr_desktop_drop
    PRIVATE ole32 oleaut32 uuid shell32 user32)
  set_target_properties(exr_desktop_drop_win32 PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON EXPORT_NAME win32)
  if(EXR_DESKTOP_DROP_TEST_HOOKS)
    target_compile_definitions(exr_desktop_drop_win32 PUBLIC EXR_DESKTOP_DROP_TEST_HOOKS=1)
  endif()
  add_library(EXReaderDesktopDrop::win32 ALIAS exr_desktop_drop_win32)
  list(APPEND exrdd_targets exr_desktop_drop_win32)
  list(APPEND exrdd_headers include/exr_desktop_drop_windows.h)
  list(APPEND exrdd_components win32)
elseif(APPLE)
  enable_language(OBJCXX)
  add_library(exr_desktop_drop_apple STATIC src/apple.mm)
  target_link_libraries(exr_desktop_drop_apple PUBLIC exr_desktop_drop "-framework Cocoa" "-framework Foundation")
  set_source_files_properties(src/apple.mm PROPERTIES COMPILE_OPTIONS "-fno-objc-arc;-fobjc-exceptions")
  set_target_properties(exr_desktop_drop_apple PROPERTIES EXPORT_NAME apple)
  add_library(EXReaderDesktopDrop::apple ALIAS exr_desktop_drop_apple)
  list(APPEND exrdd_targets exr_desktop_drop_apple)
  list(APPEND exrdd_headers include/exr_desktop_drop_apple.h)
  list(APPEND exrdd_components apple)
else()
  find_package(PkgConfig QUIET)
  if(PkgConfig_FOUND AND EXR_DESKTOP_DROP_GTK)
    pkg_check_modules(GTK3 QUIET IMPORTED_TARGET gtk+-3.0)
  endif()
  if(GTK3_FOUND)
    add_library(exr_desktop_drop_gtk STATIC src/gtk.c)
    target_link_libraries(exr_desktop_drop_gtk PUBLIC exr_desktop_drop PkgConfig::GTK3)
    set_target_properties(exr_desktop_drop_gtk PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON EXPORT_NAME gtk)
    add_library(EXReaderDesktopDrop::gtk ALIAS exr_desktop_drop_gtk)
    list(APPEND exrdd_targets exr_desktop_drop_gtk)
    list(APPEND exrdd_headers include/exr_desktop_drop_gtk.h)
    list(APPEND exrdd_components gtk)
    message(STATUS "EXReaderDesktopDrop: GTK3 ${GTK3_VERSION} adapter enabled")
  else()
    message(STATUS "EXReaderDesktopDrop: GTK3 not found, building the portable core only")
  endif()
endif()

install(TARGETS ${exrdd_targets} EXPORT EXReaderDesktopDropTargets ARCHIVE DESTINATION lib)
install(FILES ${exrdd_headers} DESTINATION include)
install(EXPORT EXReaderDesktopDropTargets NAMESPACE EXReaderDesktopDrop:: DESTINATION lib/cmake/EXReaderDesktopDrop)

set(_exrdd_config "include(CMakeFindDependencyMacro)\n")
if("gtk" IN_LIST exrdd_components)
  string(APPEND _exrdd_config
    "if(\"gtk\" IN_LIST EXReaderDesktopDrop_FIND_COMPONENTS)\n"
    "  find_dependency(PkgConfig)\n"
    "  pkg_check_modules(GTK3 REQUIRED IMPORTED_TARGET gtk+-3.0)\n"
    "  set(EXReaderDesktopDrop_gtk_FOUND TRUE)\n"
    "endif()\n")
endif()
string(APPEND _exrdd_config
  "include(\"\${CMAKE_CURRENT_LIST_DIR}/EXReaderDesktopDropTargets.cmake\")\n"
  "set(EXReaderDesktopDrop_VERSION 0.1.0)\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopDropConfig.cmake" "${_exrdd_config}")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopDropConfig.cmake"
  DESTINATION lib/cmake/EXReaderDesktopDrop)

include(CMakePackageConfigHelpers)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopDropConfigVersion.cmake"
  VERSION 0.1.0 COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopDropConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderDesktopDrop)
