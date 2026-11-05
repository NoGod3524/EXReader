cmake_minimum_required(VERSION 3.24)
project(EXReaderWindowsNativeQualification LANGUAGES C)
if(NOT WIN32)
  message(FATAL_ERROR "This qualification requires native Windows")
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
find_package(EXReader CONFIG REQUIRED COMPONENTS core library)
# Frozen scanner and provider closure controls remain byte-identical.
add_subdirectory(../recovery_preflight_20261029 frozen-preflight)
set_property(GLOBAL PROPERTY PREFLIGHT_SEEN "")
# record_link_target writes link-closure.txt in the caller directory.
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/link-closure.txt" "Native consumer dependency inventory\n")
record_link_target(EXReader::exr_library)
record_link_target(EXReader::exr_core)
add_executable(migration-windows-native probe.c
  ../../../extras/migration/src/lm_recovery_win32_platform.c
  ../../../extras/migration/src/lm_util.c
  ../../../extras/migration/src/lm_mirror.c)
target_include_directories(migration-windows-native PRIVATE
  ../../../extras/migration/src "${SQLITE_HEADER_DIR}")
target_compile_definitions(migration-windows-native PRIVATE
  _WIN32_WINNT=0x0A00 _CRT_SECURE_NO_WARNINGS)
target_compile_options(migration-windows-native PRIVATE /utf-8)
set_target_properties(migration-windows-native PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_link_libraries(migration-windows-native PRIVATE EXReader::exr_library EXReader::exr_core advapi32 bcrypt psapi)
target_link_options(migration-windows-native PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/native-provider.map")
