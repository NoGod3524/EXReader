# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderAccountProfiles VERSION 0.1.0 LANGUAGES C)

# Optional package: no SDK, product catalog, revision store or SQLite is needed.
# It records non-secret account profiles and the isolated directory mapping the
# host later feeds to the existing reader_session package.
add_library(reader_account_profiles STATIC
  src/account_profiles.c
  src/document.c
  src/file.c)
target_compile_features(reader_account_profiles PUBLIC c_std_11)
set_target_properties(reader_account_profiles PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(reader_account_profiles PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(MSVC)
  target_compile_options(reader_account_profiles PRIVATE /W4 /WX /utf-8)
  target_compile_definitions(reader_account_profiles PRIVATE _CRT_SECURE_NO_WARNINGS)
else()
  target_compile_options(reader_account_profiles PRIVATE -Wall -Wextra -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_account_profiles EXPORT EXReaderAccountProfilesTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_account_profiles.h DESTINATION include)
install(EXPORT EXReaderAccountProfilesTargets NAMESPACE EXReaderAccountProfiles:: DESTINATION lib/cmake/EXReaderAccountProfiles)
configure_package_config_file(EXReaderAccountProfilesConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAccountProfilesConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderAccountProfiles)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderAccountProfilesConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAccountProfilesConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAccountProfilesConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderAccountProfiles)
