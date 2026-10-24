# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_keyboard_actions_probes LANGUAGES C)
if(APPLE)
  enable_language(OBJC)
endif()
if(MSVC)
  add_compile_options(/utf-8)
endif()

# The probe is a real platform application: it links the installed package plus
# the native GUI library of the runner and nothing from the source tree.
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderKeyboardActions 0.1.0 EXACT CONFIG REQUIRED)

if(WIN32)
  add_executable(keyboard-probe win32_probe.c)
  target_link_libraries(keyboard-probe PRIVATE EXReaderKeyboardActions::reader_keyboard_actions
    user32 comctl32)
elseif(APPLE)
  add_executable(keyboard-probe apple_probe.m)
  target_link_libraries(keyboard-probe PRIVATE EXReaderKeyboardActions::reader_keyboard_actions
    "-framework Cocoa")
  set_target_properties(keyboard-probe PROPERTIES
    XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED NO
    MACOSX_DEPLOYMENT_TARGET "11.0")
elseif(UNIX)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(GTK3 REQUIRED IMPORTED_TARGET gtk+-3.0)
  pkg_check_modules(XTST REQUIRED IMPORTED_TARGET xtst)
  pkg_check_modules(XLIB REQUIRED IMPORTED_TARGET x11)
  add_executable(keyboard-probe linux_probe.c)
  target_link_libraries(keyboard-probe PRIVATE EXReaderKeyboardActions::reader_keyboard_actions
    PkgConfig::GTK3 PkgConfig::XTST PkgConfig::XLIB)
endif()
