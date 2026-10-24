# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_localization_consumers LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# The two installed consumers below see only the installed package and its
# public header: no source directory, no test hook and no build tree of the
# package itself is referenced.
find_package(EXReaderLocalization 0.1.0 EXACT CONFIG REQUIRED)
find_package(Threads REQUIRED)

add_executable(localization-c-consumer c_consumer.c)
target_link_libraries(localization-c-consumer PRIVATE EXReaderLocalization::reader_localization)
target_compile_features(localization-c-consumer PRIVATE c_std_11)
add_executable(localization-cpp-consumer cpp_consumer.cpp)
target_link_libraries(localization-cpp-consumer PRIVATE EXReaderLocalization::reader_localization Threads::Threads)
if(MSVC)
  target_compile_options(localization-c-consumer PRIVATE /W4 /WX)
  target_compile_options(localization-cpp-consumer PRIVATE /W4 /WX)
else()
  target_compile_options(localization-c-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(localization-cpp-consumer PRIVATE -Wall -Wextra -Werror)
endif()

# The worker alone is built from source with test hooks. It is the only
# consumer that can drop a translation or install a self-inconsistent
# template, so the shipped library keeps no mutable global state.
if(EXR_LOCALIZATION_SOURCE)
  add_library(localization_test_impl STATIC
    "${EXR_LOCALIZATION_SOURCE}/localization.c"
    "${EXR_LOCALIZATION_SOURCE}/catalog.c"
    "${EXR_LOCALIZATION_SOURCE}/sha256.c")
  target_compile_definitions(localization_test_impl PRIVATE READER_LOCALIZATION_TEST_HOOKS=1)
  target_compile_features(localization_test_impl PUBLIC c_std_11)
  target_include_directories(localization_test_impl PUBLIC
    "${EXR_LOCALIZATION_INCLUDE}" "${EXR_LOCALIZATION_SOURCE}")
  add_executable(localization-worker worker.c)
  target_link_libraries(localization-worker PRIVATE localization_test_impl)
  target_compile_features(localization-worker PRIVATE c_std_11)
  if(MSVC)
    target_compile_options(localization_test_impl PRIVATE /W4 /WX /utf-8)
    target_compile_options(localization-worker PRIVATE /W4 /WX /utf-8)
  else()
    target_compile_options(localization_test_impl PRIVATE -Wall -Wextra -Werror)
    target_compile_options(localization-worker PRIVATE -Wall -Wextra -Werror)
  endif()
endif()
