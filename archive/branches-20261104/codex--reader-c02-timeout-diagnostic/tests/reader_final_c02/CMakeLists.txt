# SPDX-License-Identifier: MIT
# Installed-public-SDK corpus seed used only by the cloud C02 performance tools.
cmake_minimum_required(VERSION 3.24)
project(EXReaderFinalC02Probes LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(EXR_SDK_VERSION "3.41.0" CACHE STRING "Exact installed SDK version")
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_executable(c02_seed seed_library.c)
if(NOT MSVC)
  target_compile_options(c02_seed PRIVATE -Wall -Wextra -Werror)
endif()
target_link_libraries(c02_seed PRIVATE EXReader::exr_core EXReader::exr_library)
