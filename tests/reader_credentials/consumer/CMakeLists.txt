# SPDX-License-Identifier: MIT
# Consumes only the installed EXReaderCredentials package.
cmake_minimum_required(VERSION 3.22)
project(CredentialsInstalledConsumer LANGUAGES C)
set(CMAKE_C_STANDARD 11)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8 /W4)
else()
  add_compile_options(-Wall -Wextra)
endif()
find_package(EXReaderCredentials 0.1 CONFIG REQUIRED)
add_executable(credentials-consumer main.c suite.c)
target_link_libraries(credentials-consumer PRIVATE EXReaderCredentials::exr_credentials)
