# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderLocalization VERSION 0.1.0 LANGUAGES C)

# Optional package: no SDK, product catalog, revision store, SQLite, host
# settings file or platform resource bundle is needed. The library owns a fixed
# zh-CN/en-US message catalog and a strict renderer; the host keeps its own
# strings and decides when to call this package.
add_library(reader_localization STATIC
  src/localization.c
  src/catalog.c
  src/sha256.c)
target_compile_features(reader_localization PUBLIC c_std_11)
set_target_properties(reader_localization PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(reader_localization PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(MSVC)
  target_compile_options(reader_localization PRIVATE /W4 /WX /utf-8)
else()
  target_compile_options(reader_localization PRIVATE -Wall -Wextra -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_localization EXPORT EXReaderLocalizationTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_localization.h DESTINATION include)
install(EXPORT EXReaderLocalizationTargets NAMESPACE EXReaderLocalization:: DESTINATION lib/cmake/EXReaderLocalization)
configure_package_config_file(EXReaderLocalizationConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalizationConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderLocalization)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalizationConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalizationConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLocalizationConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderLocalization)
