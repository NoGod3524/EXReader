cmake_minimum_required(VERSION 3.24)
project(EXReaderRecoveryHandoff LANGUAGES C)
if(WIN32)
  message(FATAL_ERROR "POSIX protocol only; Windows is not qualified")
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
find_package(EXReader CONFIG REQUIRED COMPONENTS core library)
# Reuse the frozen whole-entry provider inventory and configure controls.
# This builds the unchanged scanner too; no predecessor file is edited.
add_subdirectory(../recovery_preflight_20261029 frozen-preflight)
add_executable(migration-recovery-handoff handoff.c
  ../../../extras/migration/src/lm_util.c
  ../../../extras/migration/src/lm_mirror.c)
target_include_directories(migration-recovery-handoff PRIVATE
  "${SQLITE_HEADER_DIR}" ../../../extras/migration/src)
target_link_libraries(migration-recovery-handoff PRIVATE EXReader::exr_library m)
set_target_properties(migration-recovery-handoff PROPERTIES
  C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(APPLE)
  target_link_options(migration-recovery-handoff PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/provider.map")
else()
  target_link_options(migration-recovery-handoff PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/provider.map")
endif()
