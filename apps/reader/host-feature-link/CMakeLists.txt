# SPDX-License-Identifier: MIT
# Installed host-link package for the five reviewed optional reader packages.
# It ships one CMake module and nothing else: no library, no copied header, no
# second SDK or store provider, no code. The module itself lives at
# tools/reader_host_feature_link.cmake in the source tree.
cmake_minimum_required(VERSION 3.24)
project(EXReaderHostFeatureLink VERSION 1.0.0 LANGUAGES NONE)

set(_exr_hfl_module "${CMAKE_CURRENT_SOURCE_DIR}/../../../tools/reader_host_feature_link.cmake")
if(NOT EXISTS "${_exr_hfl_module}")
  message(FATAL_ERROR "EXReaderHostFeatureLink needs tools/reader_host_feature_link.cmake")
endif()

include(CMakePackageConfigHelpers)
install(FILES "${_exr_hfl_module}"
  DESTINATION lib/cmake/EXReaderHostFeatureLink RENAME EXReaderHostFeatureLink.cmake)
install(FILES README.md DESTINATION share/exreader-host-feature-link)
configure_package_config_file(EXReaderHostFeatureLinkConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderHostFeatureLinkConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderHostFeatureLink)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderHostFeatureLinkConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderHostFeatureLinkConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderHostFeatureLinkConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderHostFeatureLink)
