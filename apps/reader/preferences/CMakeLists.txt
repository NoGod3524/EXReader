# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderPreferences VERSION 0.1.0 LANGUAGES C)

# Optional package: no SDK, product catalog, revision store, SQLite or host
# settings file is needed. The host applies these values through the public SDK.
add_library(reader_preferences STATIC
  src/preferences.c
  src/json.c
  src/file.c)
target_compile_features(reader_preferences PUBLIC c_std_11)
set_target_properties(reader_preferences PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(reader_preferences PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(UNIX)
  target_link_libraries(reader_preferences PUBLIC m)
endif()
if(MSVC)
  target_compile_options(reader_preferences PRIVATE /W4 /WX /utf-8)
else()
  target_compile_options(reader_preferences PRIVATE -Wall -Wextra -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_preferences EXPORT EXReaderPreferencesTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_preferences.h DESTINATION include)
install(EXPORT EXReaderPreferencesTargets NAMESPACE EXReaderPreferences:: DESTINATION lib/cmake/EXReaderPreferences)
configure_package_config_file(EXReaderPreferencesConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderPreferencesConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderPreferences)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderPreferencesConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderPreferencesConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderPreferencesConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderPreferences)
