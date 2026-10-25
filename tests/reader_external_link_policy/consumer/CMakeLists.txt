# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_external_link_policy_consumers LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# Every target below except link_test_impl resolves EXReaderLinkPolicy from the
# install prefix only. The package does not depend on the reading SDK; the SDK
# consumer additionally consumes the installed frozen SDK for the navigation
# hand-off, exactly like a host would.
find_package(EXReaderLinkPolicy 0.1.0 EXACT CONFIG REQUIRED)

add_executable(link-probe link_probe.c)
target_link_libraries(link-probe PRIVATE EXReaderLinkPolicy::reader_link_policy)
set_target_properties(link-probe PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)

find_package(Threads REQUIRED)
add_executable(link-cpp-consumer link_cpp_consumer.cpp)
target_link_libraries(link-cpp-consumer PRIVATE EXReaderLinkPolicy::reader_link_policy Threads::Threads)

# Negative control for the symbol audit in check_link_policy.py. It is compiled
# and archived, never executed; the auditor must find its forbidden references,
# which shows the audit can actually detect a network or process dependency.
add_library(link-unsafe-control STATIC control_unsafe.c)
set_target_properties(link-unsafe-control PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)

# The worker alone is built from source with the test hooks. The installed
# consumers above never see READER_LINK_POLICY_TEST_HOOKS, so allocation failure
# and cancellation points cannot be steered through the shipped library.
if(EXR_LINK_POLICY_SOURCE)
  add_library(link_test_impl STATIC "${EXR_LINK_POLICY_SOURCE}/policy.c")
  target_compile_definitions(link_test_impl PRIVATE READER_LINK_POLICY_TEST_HOOKS=1)
  target_compile_features(link_test_impl PUBLIC c_std_11)
  target_include_directories(link_test_impl PUBLIC
    "${EXR_LINK_POLICY_INCLUDE}" "${EXR_LINK_POLICY_SOURCE}")
  add_executable(link-worker link_worker.c)
  target_link_libraries(link-worker PRIVATE link_test_impl)
  set_target_properties(link-worker PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
endif()

set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed reading SDK")
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core)
add_executable(link-sdk-consumer link_sdk_consumer.c)
target_link_libraries(link-sdk-consumer PRIVATE
  EXReaderLinkPolicy::reader_link_policy EXReader::exr_core)
set_target_properties(link-sdk-consumer PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)

set(LINK_STRICT_TARGETS link-probe link-cpp-consumer link-unsafe-control link-sdk-consumer)
if(EXR_LINK_POLICY_SOURCE)
  list(APPEND LINK_STRICT_TARGETS link_test_impl link-worker)
endif()
foreach(target IN LISTS LINK_STRICT_TARGETS)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /WX /utf-8)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
  endif()
endforeach()
