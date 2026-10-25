# SPDX-License-Identifier: MIT
# Default reading build isolation: configured against the prefix snapshot taken
# immediately after the frozen SDK install, before any optional module exists.
# It must find the SDK components, must NOT discover any optional package and
# must expose no module target.
cmake_minimum_required(VERSION 3.24)
project(EXReaderDefaultReadingOnly LANGUAGES C)
if(MSVC)
  # Every installed module is built with the static MSVC runtime; a consumer
  # that keeps the default /MD cannot link them, so state it here as well.
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
if(NOT EXR_MODULE_PREFIX)
  message(FATAL_ERROR "EXR_MODULE_PREFIX must name the SDK-only prefix snapshot")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
list(PREPEND CMAKE_PREFIX_PATH "${EXR_MODULE_PREFIX}")
set(EXR_SDK_VERSION "3.40.0" CACHE STRING "Exact installed reading SDK")
find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library)

set(optional_packages
  EXReaderThumbnails EXReaderReadingCommands EXReaderAnnotationView
  EXReaderAnnotationExport EXReaderLocalDownloads
  EXReaderCloudImport
  EXReaderBulkOrganization
  EXReaderLinkPolicy
  EXReaderJumpHistory
  EXReaderKeyboardActions
  EXReaderBookInformation
  EXReaderSyncView
  EXReaderAccountProfiles
  EXReaderProductCatalog EXReaderRevisions EXReaderCommands EXReaderDesktopMetadata
  EXReaderReadingState EXReaderSearch EXReaderSession EXReaderSync EXReaderPreferences
  EXReaderBatchImport EXReaderSideload EXReaderWebDAV EXReaderCredentials)
set(found "")
set(targets "")
foreach(package IN LISTS optional_packages)
  find_package(${package} CONFIG QUIET)
  if(${package}_FOUND)
    list(APPEND found "${package}")
  endif()
endforeach()
foreach(target IN ITEMS
  EXReaderThumbnails::reader_thumbnails EXReaderReadingCommands::reader_reading_commands
  EXReaderAnnotationView::reader_annotation_view EXReaderAnnotationExport::reader_annotation_export
  EXReaderLocalDownloads::reader_local_downloads
  EXReaderCloudImport::reader_cloud_import
  EXReaderBulkOrganization::reader_bulk
  EXReaderLinkPolicy::reader_link_policy
  EXReaderJumpHistory::reader_jump_history
  EXReaderKeyboardActions::reader_keyboard_actions
  EXReaderBookInformation::reader_book_information
  EXReaderSyncView::reader_sync_view
  EXReaderAccountProfiles::reader_account_profiles
    EXReaderProductCatalog::reader_catalog EXReaderRevisions::reader_revisions
    EXReaderCommands::reader_commands EXReaderDesktopMetadata::reader_desktop_metadata
    EXReaderReadingState::reader_reading_state EXReaderSearch::reader_search
    EXReaderSession::reader_session EXReaderSync::reader_sync
    EXReaderPreferences::reader_preferences EXReaderBatchImport::reader_batch_import
    EXReaderSideload::exr_sideload EXReaderWebDAV::exr_webdav
    EXReaderCredentials::exr_credentials)
  if(TARGET ${target})
    list(APPEND targets "${target}")
  endif()
endforeach()

function(exr_json_list values out)
  set(json "")
  foreach(value IN LISTS values)
    if(json)
      string(APPEND json ", ")
    endif()
    string(APPEND json "\"" "${value}" "\"")
  endforeach()
  set(${out} "[${json}]" PARENT_SCOPE)
endfunction()

exr_json_list("${found}" found_json)
exr_json_list("${targets}" targets_json)
if(EXReader_core_FOUND)
  set(core_found "true")
else()
  set(core_found "false")
endif()
if(EXReader_library_FOUND)
  set(library_found "true")
else()
  set(library_found "false")
endif()
string(REPLACE "\\" "\\\\" version "${EXReader_VERSION}")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/sdk-only-report.json"
  "{\"sdk_version\": \"${version}\", \"core_found\": ${core_found}, \"library_found\": ${library_found},\n"
  " \"optional_packages_found\": ${found_json},\n"
  " \"optional_targets_visible\": ${targets_json}}\n")

add_executable(default-reading-consumer main.c)
target_link_libraries(default-reading-consumer PRIVATE EXReader::exr_core)
