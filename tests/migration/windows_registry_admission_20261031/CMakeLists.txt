cmake_minimum_required(VERSION 3.24)
project(CoordinatorRegistryInstalledConsumer LANGUAGES C CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(TO_CMAKE_PATH "${WH_PREFIX}" WH_PREFIX)
list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
find_package(EXReader 3.42.0 EXACT CONFIG REQUIRED COMPONENTS core library)
add_executable(coordinator-registry-check registry_test.c)
target_compile_options(coordinator-registry-check PRIVATE /utf-8 /W4 /WX)
target_compile_definitions(coordinator-registry-check PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602 "CANDIDATE_SOURCE_SHA=\"${SOURCE_SHA}\"")
target_include_directories(coordinator-registry-check PRIVATE
 "${WH_PREFIX}/include/exreader-coordinator-native"
 "${WH_PREFIX}/include/exreader-coordinator-cas"
 "${WH_PREFIX}/include/exreader-migration-coordinator-hardening")
target_link_libraries(coordinator-registry-check PRIVATE
 "${WH_PREFIX}/lib/exreader-coordinator-native.lib"
 "${WH_PREFIX}/lib/exreader-coordinator-cas.lib"
 "${WH_PREFIX}/lib/exreader-migration-coordinator-hardening.lib"
 EXReader::exr_library advapi32)
set_target_properties(coordinator-registry-check PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON LINKER_LANGUAGE CXX)
