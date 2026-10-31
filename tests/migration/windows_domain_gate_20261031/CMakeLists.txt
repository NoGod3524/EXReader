cmake_minimum_required(VERSION 3.16)
project(CoordinatorPersistentGateConsumer LANGUAGES C)
if(NOT WIN32 OR NOT C01_SOURCE)
  message(FATAL_ERROR "Native Windows and the exact frozen C01 source are required")
endif()
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(coordinator-domain-check gate_test.c "${C01_SOURCE}/src/lm_win_lease.c")
target_compile_options(coordinator-domain-check PRIVATE /utf-8 /W4 /WX)
target_compile_definitions(coordinator-domain-check PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602 "CANDIDATE_SOURCE_SHA=\"${SOURCE_SHA}\"")
target_include_directories(coordinator-domain-check PRIVATE
 "${WH_PREFIX}/include/exreader-coordinator-native"
 "${WH_PREFIX}/include/exreader-coordinator-cas"
 "${WH_PREFIX}/include/exreader-migration-coordinator-hardening"
 "${C01_SOURCE}/include")
target_link_libraries(coordinator-domain-check PRIVATE
 "${WH_PREFIX}/lib/exreader-coordinator-native.lib"
 "${WH_PREFIX}/lib/exreader-coordinator-cas.lib"
 "${WH_PREFIX}/lib/exreader-migration-coordinator-hardening.lib")
set_target_properties(coordinator-domain-check PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
