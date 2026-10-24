# SPDX-License-Identifier: MIT
# Negative gate: a package whose declared dependency is absent must fail
# find_package(), never resolve against a stale or partial prefix.
cmake_minimum_required(VERSION 3.24)
project(EXReaderMissingDependency LANGUAGES C)
if(NOT EXR_MODULE_PREFIX)
  message(FATAL_ERROR "EXR_MODULE_PREFIX must name the single installed prefix")
endif()
list(PREPEND CMAKE_PREFIX_PATH "${EXR_MODULE_PREFIX}")
find_package(EXReaderSync 0.1.0 EXACT CONFIG REQUIRED)
add_executable(missing-dependency main.c)
target_link_libraries(missing-dependency PRIVATE EXReaderSync::reader_sync)
