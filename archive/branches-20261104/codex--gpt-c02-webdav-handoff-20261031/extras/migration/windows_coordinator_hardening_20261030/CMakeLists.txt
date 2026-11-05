# SPDX-License-Identifier: MIT
# Standalone coordinator hardening library. No SDK or host dependency.
cmake_minimum_required(VERSION 3.16)
project(EXReaderMigrationCoordinatorHardening20261030 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4 /WX)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
else()
  add_compile_options(-Wall -Wextra -Werror)
endif()
add_library(exreader-migration-coordinator-hardening STATIC src/wh_core.c src/wh_digest.c)
target_include_directories(exreader-migration-coordinator-hardening PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/exreader-migration-coordinator-hardening>)
set_target_properties(exreader-migration-coordinator-hardening PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
install(TARGETS exreader-migration-coordinator-hardening ARCHIVE DESTINATION lib)
install(FILES include/exr_wh.h DESTINATION include/exreader-migration-coordinator-hardening)
