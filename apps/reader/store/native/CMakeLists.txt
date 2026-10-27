# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderProductCatalog VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
include(FetchContent)
# A product dependency with its own public SQLite API; no SDK private headers.
# Keep the same upstream version and compile limits as the frozen reading SDK.
FetchContent_Declare(reader_catalog_sqlite_source
  URL "https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip"
  URL_HASH SHA256=68e913b0fe8ec6b4e5f391c594a28872884e80d6cd042a1e50c957be46b5aa4d)
FetchContent_MakeAvailable(reader_catalog_sqlite_source)
add_library(reader_catalog_sqlite STATIC "${reader_catalog_sqlite_source_SOURCE_DIR}/sqlite3.c")
target_include_directories(reader_catalog_sqlite PUBLIC
  $<BUILD_INTERFACE:${reader_catalog_sqlite_source_SOURCE_DIR}>
  $<INSTALL_INTERFACE:include/exreader-product>)
target_compile_definitions(reader_catalog_sqlite PRIVATE SQLITE_THREADSAFE=1 SQLITE_DQS=0
  SQLITE_DEFAULT_FOREIGN_KEYS=1 SQLITE_OMIT_LOAD_EXTENSION SQLITE_MAX_LENGTH=2147483647)
find_package(Threads REQUIRED)
target_link_libraries(reader_catalog_sqlite PUBLIC Threads::Threads ${CMAKE_DL_LIBS})
if(UNIX)
  target_link_libraries(reader_catalog_sqlite PUBLIC m)
endif()
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../001_catalog.sql" catalog_sql)
string(REPLACE "\\" "\\\\" catalog_sql "${catalog_sql}")
string(REPLACE "\"" "\\\"" catalog_sql "${catalog_sql}")
string(REPLACE "\n" "\\n\"\n\"" catalog_sql "${catalog_sql}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/catalog_migration.h"
  "/* Generated from the unchanged product migration. */\nstatic const char catalog_migration[] = \"${catalog_sql}\";\n")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../002_originals.sql" originals_sql)
string(REPLACE "\\" "\\\\" originals_sql "${originals_sql}")
string(REPLACE "\"" "\\\"" originals_sql "${originals_sql}")
string(REPLACE "\n" "\\n\"\n\"" originals_sql "${originals_sql}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/originals_migration.h"
  "static const char originals_migration[] = \"${originals_sql}\";\n")
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/../003_original_staging.sql" staging_sql)
string(REPLACE "\\" "\\\\" staging_sql "${staging_sql}")
string(REPLACE "\"" "\\\"" staging_sql "${staging_sql}")
string(REPLACE "\n" "\\n\"\n\"" staging_sql "${staging_sql}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/staging_migration.h"
  "static const char staging_migration[] = \"${staging_sql}\";\n")
add_library(reader_catalog STATIC catalog.c)
target_include_directories(reader_catalog PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
  $<INSTALL_INTERFACE:include/exreader-product>
  PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(reader_catalog PRIVATE reader_catalog_sqlite Threads::Threads)
if(MSVC)
  target_compile_options(reader_catalog PRIVATE /W4 /WX)
else()
  target_compile_options(reader_catalog PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_catalog reader_catalog_sqlite EXPORT EXReaderProductCatalogTargets ARCHIVE DESTINATION lib)
install(FILES catalog.h "${reader_catalog_sqlite_source_SOURCE_DIR}/sqlite3.h"
  DESTINATION include/exreader-product)
install(FILES ../001_catalog.sql ../002_originals.sql ../003_original_staging.sql ../../../../licenses/sqlite-public-domain.txt
  DESTINATION share/exreader-product)
install(EXPORT EXReaderProductCatalogTargets NAMESPACE EXReaderProductCatalog::
  DESTINATION lib/cmake/EXReaderProductCatalog)
configure_package_config_file(EXReaderProductCatalogConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderProductCatalogConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderProductCatalog)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderProductCatalogConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderProductCatalogConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderProductCatalogConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderProductCatalog)
if(PROJECT_IS_TOP_LEVEL)
  enable_testing()
  add_executable(reader-originals-check ../../../../tests/reader_catalog/originals_check.c)
  target_link_libraries(reader-originals-check PRIVATE reader_catalog reader_catalog_sqlite Threads::Threads)
  add_test(NAME product-originals COMMAND reader-originals-check "${CMAKE_CURRENT_BINARY_DIR}/originals-check.db")
  add_executable(reader-catalog-check ../../../../tests/reader_catalog/native_catalog_check.c)
  target_link_libraries(reader-catalog-check PRIVATE reader_catalog reader_catalog_sqlite Threads::Threads)
  add_test(NAME native-product-catalog COMMAND reader-catalog-check
    "${CMAKE_CURRENT_BINARY_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/../001_catalog.sql")
endif()
