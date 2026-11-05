# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderWebDAVManagedCleanupTests LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(EXR_WC_CORE_SOURCE "" CACHE PATH "Separate checkout of the pinned core commit")
set(_core_c "${EXR_WC_CORE_SOURCE}/extras/webdav-cleanup/src/cleanup_posix.c")
set(_core_include "${EXR_WC_CORE_SOURCE}/extras/webdav-cleanup/include")
if(NOT EXISTS "${_core_c}" OR NOT EXISTS "${_core_include}/exr_webdav_cleanup.h")
  message(FATAL_ERROR "EXR_WC_CORE_SOURCE must name the pinned core checkout")
endif()
find_package(EXReaderWebDAVCleanup 0.1.0 EXACT REQUIRED CONFIG)

# Ordinary consumer: installed package only, no hooks.
add_executable(wc-consumer worker.c)
target_link_libraries(wc-consumer PRIVATE EXReaderWebDAVCleanup::exr_webdav_cleanup)
target_compile_options(wc-consumer PRIVATE -Wall -Wextra -Wpedantic -Werror)

# Hook worker: the same core source compiled directly with a PRIVATE macro;
# it never links the installed archive.
add_executable(wc-hookworker worker.c "${_core_c}")
target_include_directories(wc-hookworker PRIVATE "${_core_include}")
target_compile_definitions(wc-hookworker PRIVATE EXR_WC_TEST_HOOKS=1)
target_compile_options(wc-hookworker PRIVATE -Wall -Wextra -Wpedantic -Werror)
