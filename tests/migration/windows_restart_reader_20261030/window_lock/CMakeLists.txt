cmake_minimum_required(VERSION 3.24)
project(WindowsRestartWindowLock LANGUAGES C)
if(NOT WIN32)
 message(FATAL_ERROR "Native Windows only")
endif()
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(EXReader 3.42.0 EXACT CONFIG REQUIRED COMPONENTS core library PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
get_filename_component(REPO_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
set(RESTART_SOURCE "${REPO_ROOT}/extras/migration/windows_restart_reader_20261030/src/lm_win_restart_reader.c")
add_executable(windows-restart-window-lock probe.c "${RESTART_SOURCE}")
target_include_directories(windows-restart-window-lock PRIVATE
 "${REPO_ROOT}/extras/migration/windows_restart_reader_20261030/include"
 "${LEASE_PREFIX}/include/exreader-migration-candidate"
 "${RECORD_PREFIX}/include/exreader-migration-candidate")
target_compile_definitions(windows-restart-window-lock PRIVATE
 LM_RR_TEST_AFTER_ACQUIRE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0A00 "SOURCE_SHA=\"${SOURCE_SHA}\"")
target_compile_options(windows-restart-window-lock PRIVATE /W4 /WX /utf-8)
# Deliberately no installed restart archive: the same source is compiled directly.
target_link_libraries(windows-restart-window-lock PRIVATE
 "${LEASE_PREFIX}/lib/exreader-migration-windows-lease.lib"
 "${RECORD_PREFIX}/lib/exreader-migration-windows-record.lib"
 EXReader::exr_library advapi32 psapi)
target_link_options(windows-restart-window-lock PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/window-lock.map")
set_target_properties(windows-restart-window-lock PROPERTIES C_STANDARD 11)
# Test-only executable; no install rule and no public hook declaration.
