# SPDX-License-Identifier: MIT
# Standalone consumer of an installed EXReader SDK (components: core + library).
# It is deliberately not part of the SDK build: configure it against the install prefix.
#   cmake -S extras/migration -B build/migration -DEXR_SDK=<prefix> -DCMAKE_BUILD_TYPE=Release
cmake_minimum_required(VERSION 3.24)
project(EXReaderLegacyMigration LANGUAGES C)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
  add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
endif()
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
find_package(EXReader CONFIG REQUIRED COMPONENTS core library)
if(NOT TARGET EXReader::exr_library)
  message(FATAL_ERROR "The installed SDK lacks the library component (build it with EXR_ENABLE_LIBRARY=ON); the migration tool cannot run without the SQLite library API.")
endif()
# SQLite's public backup API snapshots an old library without opening it through
# the newer SDK (which would upgrade the original in place). The installed SDK
# supplies the linked SQLite implementation; use the matching pinned header.
include(FetchContent)
FetchContent_Declare(migration_sqlite_header URL "https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip" URL_HASH SHA256=68e913b0fe8ec6b4e5f391c594a28872884e80d6cd042a1e50c957be46b5aa4d)
FetchContent_MakeAvailable(migration_sqlite_header)
add_executable(exreader-legacy-migrate src/lm_main.c src/lm_pack.c src/lm_util.c)
target_include_directories(exreader-legacy-migrate PRIVATE "${migration_sqlite_header_SOURCE_DIR}")
target_link_libraries(exreader-legacy-migrate PRIVATE EXReader::exr_library)
set_target_properties(exreader-legacy-migrate PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
add_executable(exreader-legacy-migrate-tx src/lm_main.c src/lm_pack.c src/lm_util.c)
target_compile_definitions(exreader-legacy-migrate-tx PRIVATE EXR_MIGRATION_TX_CANDIDATE=1)
target_include_directories(exreader-legacy-migrate-tx PRIVATE "${migration_sqlite_header_SOURCE_DIR}")
target_link_libraries(exreader-legacy-migrate-tx PRIVATE EXReader::exr_library)
set_target_properties(exreader-legacy-migrate-tx PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(WIN32)
  target_link_libraries(exreader-legacy-migrate PRIVATE psapi)
  target_link_libraries(exreader-legacy-migrate-tx PRIVATE psapi)
else()
  target_link_libraries(exreader-legacy-migrate PRIVATE m)
  target_link_libraries(exreader-legacy-migrate-tx PRIVATE m)
endif()
install(TARGETS exreader-legacy-migrate RUNTIME DESTINATION bin)
install(TARGETS exreader-legacy-migrate-tx RUNTIME DESTINATION bin)
install(FILES exporter/exr-legacy-export.js exporter/backup_to_pack.py
  DESTINATION share/exreader-legacy-migration/exporter)
install(FILES ../../docs/WP12-LEGACY-MIGRATION.md ../../docs/WP12-MIGRATION-REVIEW.md ../../LICENSE
  DESTINATION share/exreader-legacy-migration)

option(EXR_MIGRATION_REVIEW_TESTS "Build public API state-editing review consumer" OFF)
if(EXR_MIGRATION_REVIEW_TESTS)
  add_executable(migration-review-edit ../../tests/migration/review_edit.c)
  target_link_libraries(migration-review-edit PRIVATE EXReader::exr_library)
endif()
