cmake_minimum_required(VERSION 3.24)
project(EXReaderPosixC02SDKAdmission LANGUAGES C CXX)
if(WIN32)
  message(FATAL_ERROR "The POSIX C02 SDK adapter requires native POSIX")
endif()
if(NOT PC02_PREFIX OR NOT WH_PREFIX OR NOT EXR_SDK)
  message(FATAL_ERROR "PC02_PREFIX, WH_PREFIX and EXR_SDK must be installed prefixes")
endif()
find_package(EXReader 3.42.0 EXACT CONFIG REQUIRED COMPONENTS library PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_library(exreader-posix-c02-sdk-admission STATIC src/pc02_sdk.c)
target_compile_features(exreader-posix-c02-sdk-admission PUBLIC c_std_11)
target_compile_options(exreader-posix-c02-sdk-admission PRIVATE -Wall -Wextra -Werror)
target_include_directories(exreader-posix-c02-sdk-admission PUBLIC
 "${CMAKE_CURRENT_SOURCE_DIR}/include" "${PC02_PREFIX}/include/exreader-posix-c02-admission")
target_link_libraries(exreader-posix-c02-sdk-admission PUBLIC
 "${PC02_PREFIX}/lib/libexreader-posix-c02-admission.a"
 "${WH_PREFIX}/lib/libexreader-migration-coordinator-hardening.a"
 EXReader::exr_library EXReader::exr_core)
option(PC02_BUILD_USER_TOOL "Build the desktop explicit enrollment tool" ON)
if(ANDROID OR CMAKE_SYSTEM_NAME STREQUAL "iOS")
  set(PC02_BUILD_USER_TOOL OFF)
endif()
if(PC02_BUILD_USER_TOOL)
  add_executable(exreader-c02-admission tools/pc02_sdk_main.c)
  target_compile_options(exreader-c02-admission PRIVATE -Wall -Wextra -Werror)
  target_link_libraries(exreader-c02-admission PRIVATE exreader-posix-c02-sdk-admission)
  install(TARGETS exreader-c02-admission RUNTIME DESTINATION bin)
endif()
install(TARGETS exreader-posix-c02-sdk-admission ARCHIVE DESTINATION lib)
install(FILES include/exr_pc02_sdk.h include/module.modulemap
 "${PC02_PREFIX}/include/exreader-posix-c02-admission/exr_pc02.h"
 DESTINATION include/exreader-c02-admission)
install(FILES "${PC02_PREFIX}/lib/libexreader-posix-c02-admission.a"
 "${WH_PREFIX}/lib/libexreader-migration-coordinator-hardening.a" DESTINATION lib)
install(FILES cmake/EXReaderC02AdmissionConfig.cmake DESTINATION lib/cmake/EXReaderC02Admission)
