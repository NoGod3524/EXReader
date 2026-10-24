# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderKeyboardActions VERSION 0.1.0 LANGUAGES C)

# Independent optional package. It reads only the preferences enum values from
# the installed EXReaderPreferences header; it opens no device, registers no
# hotkey and links no platform UI library.
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_keyboard_actions STATIC src/keyboard_actions.c src/native.c)
target_compile_features(reader_keyboard_actions PUBLIC c_std_11)
set_target_properties(reader_keyboard_actions PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(reader_keyboard_actions PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_keyboard_actions PUBLIC EXReaderPreferences::reader_preferences)
if(UNIX)
  find_package(Threads REQUIRED)
  target_link_libraries(reader_keyboard_actions PUBLIC Threads::Threads)
endif()
if(MSVC)
  target_compile_options(reader_keyboard_actions PRIVATE /W4 /WX /utf-8)
else()
  target_compile_options(reader_keyboard_actions PRIVATE -Wall -Wextra -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_keyboard_actions EXPORT EXReaderKeyboardActionsTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_keyboard_actions.h include/reader_keyboard_actions.hpp DESTINATION include)
install(EXPORT EXReaderKeyboardActionsTargets NAMESPACE EXReaderKeyboardActions::
  DESTINATION lib/cmake/EXReaderKeyboardActions)
configure_package_config_file(EXReaderKeyboardActionsConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderKeyboardActionsConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderKeyboardActions)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderKeyboardActionsConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderKeyboardActionsConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderKeyboardActionsConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderKeyboardActions)
