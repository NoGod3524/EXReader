# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderProductCatalog VERSION 0.1.0 LANGUAGES C CXX)
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

# Product-owned originals are independent of the frozen SDK ABI.
# Exact dependency hook; independent of old builders' CMAKE_PREFIX_PATH overrides.
set(_hash_prefix "${READER_ORIGINAL_HASH_PREFIX}")
set(_hash_env "$ENV{EXREADER_ORIGINAL_HASH_PREFIX}")
if(NOT _hash_prefix)
  set(_hash_prefix "${_hash_env}")
endif()
if(NOT IS_ABSOLUTE "${_hash_prefix}" OR NOT IS_DIRECTORY "${_hash_prefix}")
  message(FATAL_ERROR "Set READER_ORIGINAL_HASH_PREFIX or EXREADER_ORIGINAL_HASH_PREFIX to the installed OPDSHash prefix")
endif()
file(REAL_PATH "${_hash_prefix}" _hash_real)
if(NOT "${_hash_prefix}" STREQUAL "${_hash_real}")
  message(FATAL_ERROR "Original hash prefix must be canonical")
endif()
if(_hash_env)
  file(REAL_PATH "${_hash_env}" _hash_env_real)
  if(NOT IS_ABSOLUTE "${_hash_env}" OR NOT "${_hash_env}" STREQUAL "${_hash_env_real}" OR
      NOT "${_hash_env_real}" STREQUAL "${_hash_real}")
    message(FATAL_ERROR "Conflicting original hash prefix selectors")
  endif()
endif()
set(_hash_config "${_hash_real}/lib/cmake/EXReaderOPDSHash")
if(DEFINED EXReaderOPDSHash_DIR AND NOT "${EXReaderOPDSHash_DIR}" STREQUAL "${_hash_config}")
  message(FATAL_ERROR "Foreign cached OPDSHash package directory")
endif()
find_package(EXReaderOPDSHash 0.1.0 EXACT CONFIG REQUIRED
  PATHS "${_hash_config}" NO_DEFAULT_PATH NO_CMAKE_FIND_ROOT_PATH)
if(NOT "${EXReaderOPDSHash_DIR}" STREQUAL "${_hash_config}")
  message(FATAL_ERROR "Original hash package discovery escaped the selected prefix")
endif()
exreader_opds_hash_validate("${_hash_real}")
add_library(reader_original_import STATIC ../../original-import/original_import.cpp)
target_compile_features(reader_original_import PRIVATE cxx_std_17)
target_include_directories(reader_original_import PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../../original-import> $<INSTALL_INTERFACE:include/exreader-product>)
target_link_libraries(reader_original_import PUBLIC reader_catalog PRIVATE EXReaderOPDSHash::opds_sha256_stream)
if(MSVC)
  target_compile_options(reader_original_import PRIVATE /W4 /WX)
else()
  target_compile_options(reader_original_import PRIVATE -Wall -Wextra -Werror)
endif()
install(TARGETS reader_original_import EXPORT EXReaderProductCatalogTargets ARCHIVE DESTINATION lib)
install(FILES ../../original-import/original_import.h DESTINATION include/exreader-product)
if(PROJECT_IS_TOP_LEVEL)
  add_executable(reader-original-import-check ../../../../tests/reader_catalog/original_import_check.cpp)
  target_link_libraries(reader-original-import-check PRIVATE reader_original_import)
endif()
