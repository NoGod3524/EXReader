# SPDX-License-Identifier: MIT
# Negative gate: a consumer may only name targets the installed export really
# defines. Naming a broken target must fail configuration, never silently
# produce an executable.
cmake_minimum_required(VERSION 3.24)
project(EXReaderBrokenTarget LANGUAGES C)
if(NOT EXR_MODULE_PREFIX)
  message(FATAL_ERROR "EXR_MODULE_PREFIX must name the single installed prefix")
endif()
list(PREPEND CMAKE_PREFIX_PATH "${EXR_MODULE_PREFIX}")
find_package(EXReaderRevisions 0.3.0 EXACT CONFIG REQUIRED)
add_executable(broken-target main.c)
target_link_libraries(broken-target PRIVATE EXReaderRevisions::reader_revisions_typo)
