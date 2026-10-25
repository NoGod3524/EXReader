# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderLinkPolicy VERSION 0.1.0 LANGUAGES C)

# Optional package: no SDK, product catalog, network, file system or process API
# is linked. The host passes the result's INTERNAL targets to the public SDK.
add_library(reader_link_policy STATIC src/policy.c)
target_compile_features(reader_link_policy PUBLIC c_std_11)
set_target_properties(reader_link_policy PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(reader_link_policy PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
if(MSVC)
  target_compile_options(reader_link_policy PRIVATE /W4 /WX /utf-8)
else()
  target_compile_options(reader_link_policy PRIVATE -Wall -Wextra -Werror)
endif()

include(CMakePackageConfigHelpers)
install(TARGETS reader_link_policy EXPORT EXReaderLinkPolicyTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_link_policy.h DESTINATION include)
install(EXPORT EXReaderLinkPolicyTargets NAMESPACE EXReaderLinkPolicy:: DESTINATION lib/cmake/EXReaderLinkPolicy)
configure_package_config_file(EXReaderLinkPolicyConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLinkPolicyConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderLinkPolicy)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderLinkPolicyConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLinkPolicyConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderLinkPolicyConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderLinkPolicy)
