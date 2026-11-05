# SPDX-License-Identifier: MIT
# Standalone full49 migration coordinator. No SDK or host dependency.
cmake_minimum_required(VERSION 3.16)
project(EXReaderMigrationCoordinator20261030 LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4 /WX)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
else()
  add_compile_options(-Wall -Wextra -Werror)
endif()
add_library(exreader-migration-coordinator STATIC src/wc_core.c src/wc_fs_provider.c)
target_include_directories(exreader-migration-coordinator PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/exreader-migration-coordinator>)
set_target_properties(exreader-migration-coordinator PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
install(TARGETS exreader-migration-coordinator ARCHIVE DESTINATION lib)
install(FILES include/exr_wc.h DESTINATION include/exreader-migration-coordinator)
install(FILES include/exr_wc_provider.h DESTINATION include/exreader-migration-coordinator/private)
