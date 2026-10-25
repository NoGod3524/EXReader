# SPDX-License-Identifier: MIT
# S08 independent consumer: installed owner packages plus the owner-built OPDS
# static library (extras/opds installs no CMake package). No owner source is
# recompiled and no assert is relaxed.
cmake_minimum_required(VERSION 3.24)
project(reader_final_s08_consumer LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  add_compile_options(/utf-8)
endif()

find_package(EXReaderCredentials 0.1.0 CONFIG REQUIRED)
find_package(EXReaderAccountProfiles 0.1.0 EXACT CONFIG REQUIRED)

if(NOT EXR_OPDS_LIB OR NOT EXR_OPDS_INCLUDE)
  message(FATAL_ERROR "EXR_OPDS_LIB and EXR_OPDS_INCLUDE are required")
endif()
add_library(exr_opds_external STATIC IMPORTED)
set_target_properties(exr_opds_external PROPERTIES IMPORTED_LOCATION "${EXR_OPDS_LIB}")
target_include_directories(exr_opds_external INTERFACE "${EXR_OPDS_INCLUDE}")
if(WIN32)
  target_link_libraries(exr_opds_external INTERFACE ws2_32)
endif()

add_executable(reader-final-s08-consumer main.c)
target_link_libraries(reader-final-s08-consumer PRIVATE
  EXReaderCredentials::exr_credentials
  EXReaderAccountProfiles::reader_account_profiles
  exr_opds_external)
if(MSVC)
  target_compile_options(reader-final-s08-consumer PRIVATE /W3)
else()
  target_compile_options(reader-final-s08-consumer PRIVATE -Wall -Wextra)
endif()
