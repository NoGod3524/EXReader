# SPDX-License-Identifier: MIT
# C09: the Windows platform entry reserved by apps/reader/desktop/CMakeLists.txt.
# Default OFF. Builds one additional explicit-raw host, EXReaderWave3, from the
# same examples/reader.c; every existing target is left exactly as it was.
option(EXR_READER_WINDOWS_WAVE3 "Windows host with the reviewed wave-3 optional packages (explicit raw3 profile)" OFF)
if(NOT EXR_READER_WINDOWS_WAVE3)
  return()
endif()
if(NOT EXR_SDK_VERSION STREQUAL "3.41.0" OR NOT READER_METADATA_PREFIX OR NOT READER_ACCOUNT_PREFIX)
  message(FATAL_ERROR "Wave-3 Windows host requires SDK 3.41.0 and the installed metadata and account prefixes")
endif()
set(EXR_W3_DESKTOP "${CMAKE_CURRENT_LIST_DIR}")
list(PREPEND CMAKE_PREFIX_PATH "${READER_ACCOUNT_PREFIX}" "${READER_METADATA_PREFIX}")
find_package(EXReaderCredentials 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSession 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSideload CONFIG REQUIRED)
find_package(EXReaderSearch 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderNavigation 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderCloudImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderBulkOrganization 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderPreferences 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingCommands 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationView 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationImport 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationExport 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSyncView 0.2.0 EXACT CONFIG REQUIRED)
# Every family member must be the explicit raw install; a legacy member never links.
foreach(_w3_target EXReaderRevisions::reader_revisions EXReaderReadingState::reader_reading_state_codec
    EXReaderReadingCommands::reader_reading_commands EXReaderAnnotationView::reader_annotation_view
    EXReaderCommands::reader_commands EXReaderSession::reader_session
    EXReaderDesktopMetadata::reader_desktop_metadata EXReaderAnnotationImport::reader_annotation_import
    EXReaderAnnotationExport::reader_annotation_export EXReaderJumpHistory::reader_jump_history
    EXReaderSyncView::reader_sync_view)
  get_target_property(_w3_defs ${_w3_target} INTERFACE_COMPILE_DEFINITIONS)
  if(NOT "EXR_READER_SELECTOR_BYTES_CANDIDATE=1" IN_LIST _w3_defs)
    message(FATAL_ERROR "Wave-3 Windows dependency belongs to the legacy family: ${_w3_target}")
  endif()
endforeach()

get_target_property(_w3_capture_defs EXReaderReadingState::reader_reading_state_codec INTERFACE_COMPILE_DEFINITIONS)
if(NOT "EXR_READER_PURE_CAPTURE_CANDIDATE=1" IN_LIST _w3_capture_defs)
  message(FATAL_ERROR "Wave-3 Windows history requires the explicitly installed pure raw capture capability")
endif()

add_library(reader_windows_records_w3 STATIC "${EXR_W3_DESKTOP}/windows_records_owner.cpp")
target_link_libraries(reader_windows_records_w3 PUBLIC EXReaderReadingCommands::reader_reading_commands
  EXReaderAnnotationView::reader_annotation_view EXReaderReadingState::reader_reading_state
  EXReaderCommands::reader_commands EXReaderProductCatalog::reader_catalog bcrypt)
target_include_directories(reader_windows_records_w3 PUBLIC "${EXR_W3_DESKTOP}")
target_compile_definitions(reader_windows_records_w3 PRIVATE EXR_READER_WINDOWS_RAW3=1)
target_link_libraries(reader_windows_records_w3 PRIVATE EXReaderSession::reader_session
  EXReaderDesktopMetadata::reader_desktop_metadata)

add_executable(EXReaderWave3 WIN32 "${EXR_W3_DESKTOP}/../../../examples/reader.c" "${EXR_W3_DESKTOP}/windows_wave3_bridge.cpp")
target_compile_definitions(EXReaderWave3 PRIVATE EXR_READER_PRODUCT_CATALOG=1 EXR_READER_DESKTOP_METADATA=1
  EXR_READER_WINDOWS_ACCOUNT=1 EXR_READER_WINDOWS_RAW3=1 EXR_READER_WINDOWS_SEARCH=1 EXR_READER_WINDOWS_NAVIGATION=1
  EXR_READER_WINDOWS_RECORDS=1 EXR_READER_WINDOWS_IMPORT_ORGANIZE=1 EXR_READER_WINDOWS_PREFERENCES=1
  EXR_READER_WINDOWS_COMPACT=1 EXR_READER_WINDOWS_WAVE3=1
  "EXR_READER_WINDOWS_PRODUCT_HEADER=\"${EXR_W3_DESKTOP}/windows_catalog.inc\"")
target_link_libraries(EXReaderWave3 PRIVATE reader_catalog_sdk EXReader::exr_core
  EXReaderDesktopMetadata::reader_desktop_metadata EXReaderSession::reader_session
  EXReaderCredentials::exr_credentials EXReaderSideload::exr_sideload
  EXReaderSearch::reader_search EXReaderNavigation::reader_navigation reader_windows_records_w3
  EXReaderCloudImport::reader_cloud_import EXReaderBulkOrganization::reader_bulk EXReaderPreferences::reader_preferences
  EXReaderAnnotationImport::reader_annotation_import EXReaderAnnotationExport::reader_annotation_export
  EXReaderFontLibrary::reader_font_library EXReaderOriginalExport::reader_original_export
  EXReaderJumpHistory::reader_jump_history EXReaderSyncView::reader_sync_view
  comdlg32 gdi32 shell32 user32 advapi32 bcrypt normaliz ole32 uuid)
if(MSVC)
  target_link_options(EXReaderWave3 PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/windows-host.map")
endif()
