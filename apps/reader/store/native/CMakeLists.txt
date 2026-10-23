# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderProductCatalog LANGUAGES C)
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
target_include_directories(reader_catalog_sqlite PUBLIC "${reader_catalog_sqlite_source_SOURCE_DIR}")
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
add_library(reader_catalog STATIC catalog.c)
target_include_directories(reader_catalog PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}"
  PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
target_link_libraries(reader_catalog PRIVATE reader_catalog_sqlite Threads::Threads)
if(MSVC)
  target_compile_options(reader_catalog PRIVATE /W4 /WX)
else()
  target_compile_options(reader_catalog PRIVATE -Wall -Wextra -Werror)
endif()
if(PROJECT_IS_TOP_LEVEL)
  enable_testing()
  add_executable(reader-catalog-check ../../../../tests/reader_catalog/native_catalog_check.c)
  target_link_libraries(reader-catalog-check PRIVATE reader_catalog reader_catalog_sqlite Threads::Threads)
  add_test(NAME native-product-catalog COMMAND reader-catalog-check
    "${CMAKE_CURRENT_BINARY_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/../001_catalog.sql")
endif()
