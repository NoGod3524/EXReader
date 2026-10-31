cmake_minimum_required(VERSION 3.22.1)
project(importprobe C)
set(CMAKE_C_STANDARD 11)
if(NOT EXR_SDK)
  message(FATAL_ERROR "EXR_SDK must point at the installed prefix")
endif()
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
list(APPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
set(EXReader_DIR "${EXR_SDK}/lib/cmake/EXReader" CACHE PATH "Installed EXReader package" FORCE)
find_package(EXReaderAndroidImportEntry CONFIG REQUIRED)
add_library(importprobe SHARED probe_native.c)
target_include_directories(importprobe PRIVATE "${EXR_ANDROID_IMPORT_ENTRY_SAMPLE_DIR}"
  "${EXR_SDK}/include" "${EXR_SDK}/include/exreader-c02-admission")
# The installed sample and its proof helper use the existing shared SDK.
target_link_libraries(importprobe PRIVATE EXReader::exreader
  $<TARGET_FILE:EXReaderAndroidImportEntry::exr_android_import_entry>
  $<TARGET_FILE:EXReaderSideload::exr_sideload>
  "${EXR_SDK}/lib/libexreader-posix-c02-sdk-admission.a"
  "${EXR_SDK}/lib/libexreader-posix-c02-admission.a"
  "${EXR_SDK}/lib/libexreader-migration-coordinator-hardening.a")
target_compile_options(importprobe PRIVATE -Wall -Wextra)
target_link_options(importprobe PRIVATE -Wl,-z,max-page-size=16384)
