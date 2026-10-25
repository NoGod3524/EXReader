# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(reader_account_profiles_consumers LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

# Installed packages only: the shipped static library and public header.
find_package(EXReaderAccountProfiles 0.1.0 EXACT CONFIG REQUIRED)

add_executable(profiles-probe probe.c)
target_link_libraries(profiles-probe PRIVATE EXReaderAccountProfiles::reader_account_profiles)

option(EXR_ACCOUNT_PROFILES_SESSION "Build the real reader_session cross-account consumer" ON)
if(EXR_ACCOUNT_PROFILES_SESSION)
  find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
  add_executable(profiles-session-consumer probe_session.cpp)
  target_link_libraries(profiles-session-consumer PRIVATE
    EXReaderAccountProfiles::reader_account_profiles
    EXReaderSession::reader_session)
endif()

if(MSVC)
  target_compile_options(profiles-probe PRIVATE /W4 /WX)
  if(TARGET profiles-session-consumer)
    target_compile_options(profiles-session-consumer PRIVATE /W4 /WX)
  endif()
else()
  target_compile_options(profiles-probe PRIVATE -Wall -Wextra -Werror)
  if(TARGET profiles-session-consumer)
    target_compile_options(profiles-session-consumer PRIVATE -Wall -Wextra -Werror)
  endif()
endif()

# The worker alone is compiled from package sources with test hooks. The
# installed consumers above never see that macro.
if(EXR_ACCOUNT_PROFILES_SOURCE)
  add_library(account_profiles_test_impl STATIC
    "${EXR_ACCOUNT_PROFILES_SOURCE}/account_profiles.c"
    "${EXR_ACCOUNT_PROFILES_SOURCE}/document.c"
    "${EXR_ACCOUNT_PROFILES_SOURCE}/file.c")
  target_compile_definitions(account_profiles_test_impl PRIVATE READER_ACCOUNT_PROFILES_TEST_HOOKS=1)
  target_compile_features(account_profiles_test_impl PUBLIC c_std_11)
  target_include_directories(account_profiles_test_impl PUBLIC "${EXR_ACCOUNT_PROFILES_INCLUDE}")
  if(MSVC)
    target_compile_options(account_profiles_test_impl PRIVATE /W4 /WX /utf-8)
    target_compile_definitions(account_profiles_test_impl PRIVATE _CRT_SECURE_NO_WARNINGS=1)
  else()
    target_compile_options(account_profiles_test_impl PRIVATE -Wall -Wextra -Werror)
  endif()
  add_executable(profiles-worker worker.c)
  target_link_libraries(profiles-worker PRIVATE account_profiles_test_impl)
  if(MSVC)
    target_compile_options(profiles-worker PRIVATE /W4 /WX /utf-8)
  else()
    target_compile_options(profiles-worker PRIVATE -Wall -Wextra -Werror)
  endif()
endif()
