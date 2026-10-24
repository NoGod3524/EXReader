# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(ReaderGTKReceivePublicInspector LANGUAGES C)
set(CMAKE_C_STANDARD 11)
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core library)
add_executable(received-sdk-inspect inspect.c)
target_link_libraries(received-sdk-inspect PRIVATE EXReader::exr_library EXReader::exr_core)
