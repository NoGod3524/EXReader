# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderSQLiteProvider VERSION 1.0.0 LANGUAGES C)
include(FetchContent)
include(CMakePackageConfigHelpers)
find_package(Threads REQUIRED)

# This public dependency is shared by the SDK and product; neither embeds it.
FetchContent_Declare(exreader_sqlite_source
  URL "https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip"
  URL_HASH SHA256=68e913b0fe8ec6b4e5f391c594a28872884e80d6cd042a1e50c957be46b5aa4d)
FetchContent_MakeAvailable(exreader_sqlite_source)
set(provider_options SQLITE_THREADSAFE=1 SQLITE_DQS=0 SQLITE_DEFAULT_FOREIGN_KEYS=1
  SQLITE_OMIT_LOAD_EXTENSION SQLITE_MAX_LENGTH=2147483647 SQLITE_ENABLE_FTS5)
file(SHA256 "${exreader_sqlite_source_SOURCE_DIR}/sqlite3.c" provider_source_hash)
string(SHA256 EXReaderSQLiteProvider_ID "${provider_source_hash};${provider_options}")
add_library(reader_sqlite3 SHARED "${exreader_sqlite_source_SOURCE_DIR}/sqlite3.c")
add_library(EXReaderSQLiteProvider::sqlite3 ALIAS reader_sqlite3)
set_target_properties(reader_sqlite3 PROPERTIES EXPORT_NAME sqlite3 VERSION ${PROJECT_VERSION}
  SOVERSION 1 C_STANDARD 11 C_STANDARD_REQUIRED YES)
target_compile_definitions(reader_sqlite3 PRIVATE ${provider_options})
target_include_directories(reader_sqlite3 PUBLIC
  $<BUILD_INTERFACE:${exreader_sqlite_source_SOURCE_DIR}>
  $<INSTALL_INTERFACE:include/exreader-sqlite>)
target_link_libraries(reader_sqlite3 PRIVATE Threads::Threads ${CMAKE_DL_LIBS})
if(UNIX)
  target_link_libraries(reader_sqlite3 PRIVATE m)
endif()
if(WIN32)
  target_compile_definitions(reader_sqlite3 PRIVATE "SQLITE_API=__declspec(dllexport)"
    "SQLITE_EXTERN=extern __declspec(dllexport)")
  target_compile_definitions(reader_sqlite3 INTERFACE "SQLITE_API=__declspec(dllimport)"
    "SQLITE_EXTERN=extern __declspec(dllimport)")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  set_target_properties(reader_sqlite3 PROPERTIES FRAMEWORK TRUE OUTPUT_NAME ReaderSQLite
    FRAMEWORK_VERSION A MACOSX_FRAMEWORK_IDENTIFIER org.exreader.sqlite3
    MACOSX_FRAMEWORK_SHORT_VERSION_STRING ${PROJECT_VERSION}
    MACOSX_FRAMEWORK_BUNDLE_VERSION ${PROJECT_VERSION}
    PUBLIC_HEADER "${exreader_sqlite_source_SOURCE_DIR}/sqlite3.h;${exreader_sqlite_source_SOURCE_DIR}/sqlite3ext.h")
endif()
if(APPLE)
  set_target_properties(reader_sqlite3 PROPERTIES INSTALL_NAME_DIR "@rpath")
endif()
if(ANDROID)
  target_link_options(reader_sqlite3 PRIVATE -Wl,-z,max-page-size=16384)
endif()
if(MSVC)
  target_link_options(reader_sqlite3 PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/sqlite-provider.map")
elseif(APPLE)
  target_link_options(reader_sqlite3 PRIVATE "LINKER:-map,${CMAKE_CURRENT_BINARY_DIR}/sqlite-provider.map")
else()
  target_link_options(reader_sqlite3 PRIVATE "LINKER:-Map,${CMAKE_CURRENT_BINARY_DIR}/sqlite-provider.map")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
  set(provider_runtime "Frameworks/ReaderSQLite.framework/ReaderSQLite")
elseif(WIN32)
  set(provider_runtime "bin/$<TARGET_FILE_NAME:reader_sqlite3>")
else()
  set(provider_runtime "lib/$<TARGET_FILE_NAME:reader_sqlite3>")
endif()
string(REPLACE ";" "\",\"" provider_options_json "${provider_options}")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/provider-$<CONFIG>.json" CONTENT
  "{\"package\":\"EXReaderSQLiteProvider\",\"version\":\"${PROJECT_VERSION}\",\"config_id\":\"${EXReaderSQLiteProvider_ID}\",\"source_sha256\":\"${provider_source_hash}\",\"runtime_library\":\"${provider_runtime}\",\"compile_options\":[\"${provider_options_json}\"]}\n")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/provider-$<CONFIG>.json"
  DESTINATION share/exreader-sqlite RENAME provider.json)
install(TARGETS reader_sqlite3 EXPORT EXReaderSQLiteProviderTargets
  RUNTIME DESTINATION bin LIBRARY DESTINATION lib ARCHIVE DESTINATION lib
  FRAMEWORK DESTINATION Frameworks PUBLIC_HEADER DESTINATION include/exreader-sqlite)
install(FILES "${exreader_sqlite_source_SOURCE_DIR}/sqlite3.h"
  "${exreader_sqlite_source_SOURCE_DIR}/sqlite3ext.h" DESTINATION include/exreader-sqlite)
install(FILES ../../licenses/sqlite-public-domain.txt DESTINATION share/exreader-sqlite)
install(EXPORT EXReaderSQLiteProviderTargets NAMESPACE EXReaderSQLiteProvider::
  DESTINATION lib/cmake/EXReaderSQLiteProvider)
configure_package_config_file(EXReaderSQLiteProviderConfig.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSQLiteProviderConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderSQLiteProvider)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderSQLiteProviderConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY ExactVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSQLiteProviderConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderSQLiteProviderConfigVersion.cmake"
  DESTINATION lib/cmake/EXReaderSQLiteProvider)

option(EXR_SQLITE_PROVIDER_BUILD_TESTS "Run the real SQLite/FTS5 provider smoke test" OFF)
if(EXR_SQLITE_PROVIDER_BUILD_TESTS)
  enable_testing()
  add_executable(sqlite-provider-check test_provider.c)
  target_link_libraries(sqlite-provider-check PRIVATE EXReaderSQLiteProvider::sqlite3)
  add_test(NAME sqlite-provider-check COMMAND sqlite-provider-check)
  set_tests_properties(sqlite-provider-check PROPERTIES LABELS "FTS5;SDKContract")
endif()
