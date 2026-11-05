# SPDX-License-Identifier: MIT
# F10 privacy probe: consumes only the installed EXReaderCredentials package.
cmake_minimum_required(VERSION 3.22)
project(F10PrivacyProbe LANGUAGES C)
set(CMAKE_C_STANDARD 11)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4 /D_CRT_SECURE_NO_WARNINGS)
else()
  add_compile_options(-Wall -Wextra)
endif()
find_package(EXReaderCredentials 0.1 CONFIG REQUIRED)
add_executable(f10-probe probe.c)
target_link_libraries(f10-probe PRIVATE EXReaderCredentials::exr_credentials)
