# SPDX-License-Identifier: MIT
# Installed-public-SDK probe used only by the cloud performance sampler.
cmake_minimum_required(VERSION 3.24)
project(EXReaderPerfGTKProbes LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
include("${EXR_SDK}/lib/cmake/EXReader/EXReaderConfigVersion.cmake")
find_package(EXReader ${PACKAGE_VERSION} EXACT CONFIG REQUIRED COMPONENTS library PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_executable(seed_library ../seed_library.c)
target_compile_options(seed_library PRIVATE -Wall -Wextra -Werror)
target_link_libraries(seed_library PRIVATE EXReader::exr_core EXReader::exr_library)
