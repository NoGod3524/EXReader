# SPDX-License-Identifier: MIT
# Explicit include only; no existing build includes this candidate.
option(EXR_WINDOWS_MIGRATION_HOST_CONTROLLER "Build unwired private lifecycle controller" OFF)
if(NOT EXR_WINDOWS_MIGRATION_HOST_CONTROLLER)
  return()
endif()
if(NOT WIN32)
  message(FATAL_ERROR "The migration host controller requires Windows")
endif()
add_library(reader_windows_migration_host STATIC
  "${CMAKE_CURRENT_LIST_DIR}/windows_migration_host.c")
target_include_directories(reader_windows_migration_host PUBLIC "${CMAKE_CURRENT_LIST_DIR}")
target_compile_features(reader_windows_migration_host PRIVATE c_std_11)
if(MSVC)
  target_compile_options(reader_windows_migration_host PRIVATE /W4 /WX)
endif()
# Deliberately no host target, installed facade provider, test source or SDK link.
