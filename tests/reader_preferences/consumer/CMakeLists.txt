# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_preferences_consumers LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# These two targets consume only the installed package and its public header.
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)

add_executable(preferences-c-consumer c_consumer.c)
target_link_libraries(preferences-c-consumer PRIVATE EXReaderPreferences::reader_preferences)
add_executable(preferences-cpp-consumer cpp_consumer.cpp)
target_link_libraries(preferences-cpp-consumer PRIVATE EXReaderPreferences::reader_preferences)
if(MSVC)
  target_compile_options(preferences-c-consumer PRIVATE /W4 /WX)
  target_compile_options(preferences-cpp-consumer PRIVATE /W4 /WX)
else()
  target_compile_options(preferences-c-consumer PRIVATE -Wall -Wextra -Werror)
  target_compile_options(preferences-cpp-consumer PRIVATE -Wall -Wextra -Werror)
endif()

# The worker alone is built from source with test hooks. Installed consumers
# above never see that macro; the shipped library cannot be paused or failed
# through environment variables.
if(EXR_PREFERENCES_SOURCE)
  add_library(preferences_test_impl STATIC
    "${EXR_PREFERENCES_SOURCE}/preferences.c"
    "${EXR_PREFERENCES_SOURCE}/json.c"
    "${EXR_PREFERENCES_SOURCE}/file.c")
  target_compile_definitions(preferences_test_impl PRIVATE READER_PREFERENCES_TEST_HOOKS=1)
  target_compile_features(preferences_test_impl PUBLIC c_std_11)
  target_include_directories(preferences_test_impl PUBLIC "${EXR_PREFERENCES_INCLUDE}")
  if(UNIX)
    target_link_libraries(preferences_test_impl PUBLIC m)
  endif()
  if(MSVC)
    target_compile_options(preferences_test_impl PRIVATE /W4 /WX /utf-8)
  else()
    target_compile_options(preferences_test_impl PRIVATE -Wall -Wextra -Werror)
  endif()
  add_executable(preferences-worker worker.c)
  target_link_libraries(preferences-worker PRIVATE preferences_test_impl)
  if(MSVC)
    target_compile_options(preferences-worker PRIVATE /W4 /WX /utf-8)
  else()
    target_compile_options(preferences-worker PRIVATE -Wall -Wextra -Werror)
  endif()
endif()
