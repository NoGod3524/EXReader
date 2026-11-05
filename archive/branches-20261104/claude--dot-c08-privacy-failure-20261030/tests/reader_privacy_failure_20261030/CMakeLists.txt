# SPDX-License-Identifier: MIT
# C08 privacy-failure probe: consumes only the installed EXReaderCredentials package.
cmake_minimum_required(VERSION 3.22)
project(C08PrivacyFailureProbe LANGUAGES C)
set(CMAKE_C_STANDARD 11)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4 /D_CRT_SECURE_NO_WARNINGS)
endif()
find_package(EXReaderCredentials 0.1 CONFIG REQUIRED)
add_executable(c08-probe probe.c)
target_link_libraries(c08-probe PRIVATE EXReaderCredentials::exr_credentials advapi32)
