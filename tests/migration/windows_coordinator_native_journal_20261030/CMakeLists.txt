cmake_minimum_required(VERSION 3.16)
project(CoordinatorNativeInstalledConsumer LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(coordinator-native-check wh3_win_test.c)
target_compile_options(coordinator-native-check PRIVATE /utf-8 /W4 /WX)
target_compile_definitions(coordinator-native-check PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602 "CANDIDATE_SOURCE_SHA=\"${SOURCE_SHA}\"")
target_include_directories(coordinator-native-check PRIVATE
 "${WH_PREFIX}/include/exreader-coordinator-native"
 "${WH_PREFIX}/include/exreader-coordinator-cas"
 "${WH_PREFIX}/include/exreader-migration-coordinator-hardening")
target_link_libraries(coordinator-native-check PRIVATE
 "${WH_PREFIX}/lib/exreader-coordinator-native.lib"
 "${WH_PREFIX}/lib/exreader-coordinator-cas.lib"
 "${WH_PREFIX}/lib/exreader-migration-coordinator-hardening.lib")
set_target_properties(coordinator-native-check PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
