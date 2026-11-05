# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_diagnostic_report_consumers LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# These two targets consume only the installed package and its public header.
find_package(EXReaderDiagnosticReport 0.1.0 CONFIG REQUIRED)

add_executable(diagnostic-c-consumer c_consumer.c)
target_link_libraries(diagnostic-c-consumer PRIVATE
  EXReaderDiagnosticReport::reader_diagnostic_report)
add_executable(diagnostic-cpp-consumer cpp_consumer.cpp)
target_link_libraries(diagnostic-cpp-consumer PRIVATE
  EXReaderDiagnosticReport::reader_diagnostic_report)
find_package(Threads REQUIRED)
add_executable(diagnostic-audit-consumer audit_consumer.cpp)
target_link_libraries(diagnostic-audit-consumer PRIVATE
  EXReaderDiagnosticReport::reader_diagnostic_report Threads::Threads)
if(MSVC)
  target_compile_options(diagnostic-c-consumer PRIVATE /W4 /WX)
  target_compile_options(diagnostic-cpp-consumer PRIVATE /W4 /WX)
  target_compile_options(diagnostic-audit-consumer PRIVATE /W4 /WX)
else()
  target_compile_options(diagnostic-c-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(diagnostic-cpp-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(diagnostic-audit-consumer PRIVATE -Wall -Wextra -Werror)
endif()

# The worker alone is built from package source with test hooks. Installed
# consumers above never see READER_DIAGNOSTIC_TEST_HOOKS; the shipped library
# cannot be paused, failed or shrunk through environment variables.
if(EXR_DIAGNOSTIC_SOURCE)
  find_package(Threads REQUIRED)
  add_library(diagnostic_test_impl STATIC
    "${EXR_DIAGNOSTIC_SOURCE}/report.c"
    "${EXR_DIAGNOSTIC_SOURCE}/io.c")
  target_compile_definitions(diagnostic_test_impl PUBLIC READER_DIAGNOSTIC_TEST_HOOKS=1)
  target_compile_features(diagnostic_test_impl PUBLIC c_std_11)
  target_include_directories(diagnostic_test_impl PUBLIC
    "${EXR_DIAGNOSTIC_INCLUDE}" "${EXR_DIAGNOSTIC_SOURCE}")
  if(MSVC)
    target_compile_options(diagnostic_test_impl PRIVATE /W4 /WX)
  else()
    target_compile_options(diagnostic_test_impl PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
  add_executable(diagnostic-worker worker.c)
  target_link_libraries(diagnostic-worker PRIVATE diagnostic_test_impl Threads::Threads)
  if(MSVC)
    target_compile_options(diagnostic-worker PRIVATE /W4 /WX)
  else()
    target_compile_options(diagnostic-worker PRIVATE -Wall -Wextra -Wpedantic -Werror)
  endif()
endif()
