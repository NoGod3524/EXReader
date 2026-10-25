# SPDX-License-Identifier: MIT
# Real Win32 product host with the optional account/sync integration. The
# shared apps/reader/desktop/CMakeLists.txt is intentionally untouched: this
# independent build compiles the same examples/reader.c with the account feature
# enabled against the installed SDK and installed product modules.
cmake_minimum_required(VERSION 3.24)
project(EXReaderWindowsAccount LANGUAGES C CXX)
if(NOT WIN32)
  message(FATAL_ERROR "The Windows account host requires Windows")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_compile_options(/utf-8)
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
find_package(Threads REQUIRED)
set(READER_METADATA_PREFIX "" CACHE PATH "Installed product catalog, revisions, commands and desktop metadata")
set(READER_ACCOUNT_PREFIX "" CACHE PATH "Installed credentials, sync, session, sideload and WebDAV modules")
if(NOT READER_METADATA_PREFIX OR NOT READER_ACCOUNT_PREFIX)
  message(FATAL_ERROR "Account integration requires READER_METADATA_PREFIX and READER_ACCOUNT_PREFIX")
endif()
list(PREPEND CMAKE_PREFIX_PATH "${READER_ACCOUNT_PREFIX}" "${READER_METADATA_PREFIX}")
find_package(EXReaderDesktopMetadata CONFIG REQUIRED)
# Revisions, commands, sessions and this host resolve one installed product
# catalog/SQLite provider rather than adding a second private catalog build.
add_library(reader_catalog ALIAS EXReaderProductCatalog::reader_catalog)
add_library(reader_catalog_sqlite ALIAS EXReaderProductCatalog::reader_catalog_sqlite)
find_package(EXReaderCredentials 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSession 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSideload CONFIG REQUIRED)
option(EXR_READER_WINDOWS_SEARCH "Enable the native bounded in-book search dialog" OFF)
option(EXR_READER_WINDOWS_NAVIGATION "Enable the native bounded directory dialog" OFF)
option(EXR_READER_WINDOWS_RECORDS "Enable native product reading records" OFF)
option(EXR_READER_WINDOWS_IMPORT_ORGANIZE "Enable native cloud import and batch organization" OFF)
if(EXR_READER_WINDOWS_IMPORT_ORGANIZE)
  find_package(EXReaderCloudImport 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderBulkOrganization 0.1.0 EXACT CONFIG REQUIRED)
endif()
if(EXR_READER_WINDOWS_RECORDS)
  find_package(EXReaderReadingCommands 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderAnnotationView 0.1.0 EXACT CONFIG REQUIRED)
  add_library(reader_windows_records STATIC ../desktop/windows_records_owner.cpp)
  target_link_libraries(reader_windows_records PUBLIC EXReaderReadingCommands::reader_reading_commands
    EXReaderAnnotationView::reader_annotation_view EXReaderReadingState::reader_reading_state
    EXReaderCommands::reader_commands EXReaderProductCatalog::reader_catalog bcrypt)
  target_include_directories(reader_windows_records PUBLIC ../desktop)
endif()
if(EXR_READER_WINDOWS_NAVIGATION)
  find_package(EXReaderNavigation 0.1.0 EXACT CONFIG REQUIRED)
endif()
if(EXR_READER_WINDOWS_SEARCH)
  find_package(EXReaderSearch 0.1.0 EXACT CONFIG REQUIRED)
endif()
set(DESKTOP "${CMAKE_CURRENT_SOURCE_DIR}/../desktop")
set(ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../..")
add_library(reader_catalog_sdk STATIC "${DESKTOP}/catalog_sdk.c")
target_include_directories(reader_catalog_sdk PUBLIC "${DESKTOP}")
target_link_libraries(reader_catalog_sdk PUBLIC reader_catalog EXReader::exr_library)
target_link_libraries(reader_catalog_sdk PRIVATE bcrypt normaliz)
target_compile_options(reader_catalog_sdk PRIVATE /W4 /WX)

function(reader_windows_account_host target)
  add_executable(${target} WIN32 "${ROOT}/examples/reader.c")
  target_compile_definitions(${target} PRIVATE EXR_READER_PRODUCT_CATALOG=1 EXR_READER_DESKTOP_METADATA=1
    EXR_READER_WINDOWS_ACCOUNT=1 "EXR_READER_WINDOWS_PRODUCT_HEADER=\"${DESKTOP}/windows_catalog.inc\"")
  target_link_libraries(${target} PRIVATE reader_catalog_sdk EXReader::exr_core
    EXReaderDesktopMetadata::reader_desktop_metadata EXReaderSession::reader_session
    EXReaderCredentials::exr_credentials EXReaderSideload::exr_sideload
    comdlg32 gdi32 shell32 user32 advapi32 bcrypt normaliz)
  if(EXR_READER_WINDOWS_SEARCH)
    target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_SEARCH=1)
    target_link_libraries(${target} PRIVATE EXReaderSearch::reader_search)
  endif()
  if(EXR_READER_WINDOWS_NAVIGATION)
    target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_NAVIGATION=1)
    target_link_libraries(${target} PRIVATE EXReaderNavigation::reader_navigation)
  endif()
  if(EXR_READER_WINDOWS_RECORDS)
    target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_RECORDS=1)
    target_link_libraries(${target} PRIVATE reader_windows_records)
  endif()
  if(EXR_READER_WINDOWS_IMPORT_ORGANIZE)
    target_compile_definitions(${target} PRIVATE EXR_READER_WINDOWS_IMPORT_ORGANIZE=1)
    target_link_libraries(${target} PRIVATE EXReaderCloudImport::reader_cloud_import EXReaderBulkOrganization::reader_bulk)
  endif()
endfunction()

reader_windows_account_host(EXReaderProduct)
target_link_options(EXReaderProduct PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/windows-host.map")

# Isolated worker/cache ownership regression and 2202-book seed, not installed.
add_executable(reader-windows-shelf-seed "${ROOT}/tests/windows_host/seed_shelf.c")
target_link_libraries(reader-windows-shelf-seed PRIVATE EXReader::exr_library)
reader_windows_account_host(EXReaderShelfReview)
target_compile_definitions(EXReaderShelfReview PRIVATE EXR_HOST_WORKER_REVIEW=1 EXR_HOST_SHELF_REVIEW=1
  "EXR_HOST_WORKER_REVIEW_HEADER=\"${ROOT}/tests/windows_host/worker_review/hooks.h\"")
