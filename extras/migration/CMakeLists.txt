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
add_executable(exreader-legacy-migrate src/lm_main.c src/lm_pack.c src/lm_util.c)
target_link_libraries(exreader-legacy-migrate PRIVATE EXReader::exr_library)
set_target_properties(exreader-legacy-migrate PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
if(WIN32)
  target_link_libraries(exreader-legacy-migrate PRIVATE psapi)
else()
  target_link_libraries(exreader-legacy-migrate PRIVATE m)
endif()
install(TARGETS exreader-legacy-migrate RUNTIME DESTINATION bin)
install(FILES exporter/exr-legacy-export.js exporter/backup_to_pack.py
  DESTINATION share/exreader-legacy-migration/exporter)
install(FILES ../../docs/WP12-LEGACY-MIGRATION.md ../../docs/WP12-MIGRATION-REVIEW.md ../../LICENSE
  DESTINATION share/exreader-legacy-migration)

option(EXR_MIGRATION_REVIEW_TESTS "Build public API state-editing review consumer" OFF)
if(EXR_MIGRATION_REVIEW_TESTS)
  add_executable(migration-review-edit ../../tests/migration/review_edit.c)
  target_link_libraries(migration-review-edit PRIVATE EXReader::exr_library)
endif()
