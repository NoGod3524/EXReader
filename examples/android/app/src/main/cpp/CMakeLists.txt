cmake_minimum_required(VERSION 3.22.1)
project(exreader_host C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)

if(NOT EXR_SDK)
  message(FATAL_ERROR "EXR_SDK must point at an installed EXReader SDK")
endif()
# The Android toolchain otherwise restricts package lookup to the NDK sysroot.
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
list(APPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
set(EXReader_DIR "${EXR_SDK}/lib/cmake/EXReader" CACHE PATH "Installed EXReader package" FORCE)
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED)

add_library(exreader_host SHARED exreader_host_jni.c)
target_link_libraries(exreader_host PRIVATE EXReader::exreader log)
target_compile_options(exreader_host PRIVATE -Wall -Wextra)
target_link_options(exreader_host PRIVATE -Wl,-z,max-page-size=16384)
