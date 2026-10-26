# SPDX-License-Identifier: MIT
# GTK owner include (C10). Included once by desktop/CMakeLists.txt after the
# existing GTK targets; absent options preserve the old graph byte for byte.
#
# EXR_READER_GTK_WAVE3 adds the five Wave 3 tools to the compact native host:
# checked annotation import, local font library leases, original export, jump
# history and a read-only sync status. Every module comes from one installed
# prefix; the host copies no parser, store or SDK.
#
# EXR_READER_GTK_RAW3 additionally selects the explicit raw0.2 installed family
# for the four tools that define one (annotation import/export, jump history and
# sync view), so the same five tools read and write the same raw store the
# Windows, Apple and Android hosts already use. The local font library and the
# original export have exactly one family and never carry the raw capability,
# so they stay exact 0.1.0 in both modes. The default (RAW3 OFF) configuration
# still resolves the original 0.1 modules and keeps its original entry.
option(EXR_READER_GTK_WAVE3 "Enable native annotation import, fonts, original export, history and sync status" OFF)
set(READER_WAVE3_PREFIX "" CACHE PATH "Installed annotation import, font library, original export, jump history and sync status packages")
if(EXR_READER_GTK_WAVE3)
  if(NOT EXR_READER_BUILD_GTK OR NOT UNIX OR APPLE)
    message(FATAL_ERROR "GTK Wave 3 tools require the Linux GTK host")
  endif()
  # The compact host exposes the tools in More. The non-compact host also links
  # the owners so the retained GTK business/a11y suites exercise the same graph.
  if(NOT EXR_READER_GTK_ACCOUNT OR NOT EXR_READER_GTK_READING_RECORDS OR NOT EXR_READER_GTK_SEARCH OR NOT EXR_READER_GTK_NAVIGATION)
    message(FATAL_ERROR "GTK Wave 3 tools borrow the account, records, search and navigation owners")
  endif()
  if(NOT EXR_SDK_VERSION STREQUAL "3.41.0" OR NOT READER_WAVE3_PREFIX)
    message(FATAL_ERROR "GTK Wave 3 tools need SDK 3.41.0 and one installed module prefix")
  endif()
  if(EXR_READER_GTK_RAW3)
    # One installed prefix carries the SDK, the raw0.2 host families and these
    # tools; a second prefix would let two families answer one find_package.
    if(NOT READER_GTK_RAW3_PREFIX)
      message(FATAL_ERROR "GTK raw Wave 3 tools need the explicit READER_GTK_RAW3_PREFIX family")
    endif()
    if(NOT "${READER_WAVE3_PREFIX}" STREQUAL "${READER_GTK_RAW3_PREFIX}")
      message(FATAL_ERROR "GTK raw Wave 3 tools must use the one installed raw prefix")
    endif()
  endif()
  list(PREPEND CMAKE_PREFIX_PATH "${READER_WAVE3_PREFIX}" "${EXR_SDK}")
  if(EXR_READER_GTK_RAW3)
    # The four family-specific tools, exact raw0.2 installs only.
    find_package(EXReaderAnnotationImport 0.2.0 EXACT CONFIG REQUIRED)
    find_package(EXReaderJumpHistory 0.2.0 EXACT CONFIG REQUIRED)
    find_package(EXReaderSyncView 0.2.0 EXACT CONFIG REQUIRED)
    if(EXR_LINUX_REVIEW_TESTS)
      find_package(EXReaderAnnotationExport 0.2.0 EXACT CONFIG REQUIRED)
    endif()
  else()
    find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
    find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
    find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
    if(EXR_LINUX_REVIEW_TESTS)
      find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
    endif()
  endif()
  # Single-family tools: their only install is 0.1.0 and they must not smuggle
  # the raw capability into a legacy host.
  find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
  if(EXR_READER_GTK_RAW3)
    # The exact version file is not the family guard: every raw0.2 imported
    # target also has to carry the capability it was configured for, each
    # package config has to live in that same installed prefix, and each
    # installed header macro has to name the raw version. The single-family
    # packages must stay outside the raw capability, in both directions.
    _exr_raw_guard_target(EXReaderAnnotationImport::reader_annotation_import "${EXReaderAnnotationImport_DIR}"
      reader_annotation_import_raw3.h READER_ANNOTATION_IMPORT_RAW3_VERSION 0.2.0 TRUE)
    _exr_raw_guard_target(EXReaderJumpHistory::reader_jump_history "${EXReaderJumpHistory_DIR}"
      reader_jump_history.h READER_JH_INSTALL_VERSION 0.2.0 TRUE)
    _exr_raw_guard_target(EXReaderSyncView::reader_sync_view "${EXReaderSyncView_DIR}"
      reader_sync_view.h READER_SYNC_VIEW_VERSION 0.2.0 TRUE)
    if(EXR_LINUX_REVIEW_TESTS)
      _exr_raw_guard_target(EXReaderAnnotationExport::reader_annotation_export "${EXReaderAnnotationExport_DIR}"
        reader_annotation_export_raw3.h READER_ANNOTATION_EXPORT_RAW3_VERSION 0.2.0 TRUE)
    endif()
    foreach(_w3_raw_pair
        "EXReaderAnnotationImport::reader_annotation_import|EXReaderAnnotationImport"
        "EXReaderJumpHistory::reader_jump_history|EXReaderJumpHistory"
        "EXReaderSyncView::reader_sync_view|EXReaderSyncView"
        "EXReaderFontLibrary::reader_font_library|EXReaderFontLibrary"
        "EXReaderOriginalExport::reader_original_export|EXReaderOriginalExport")
      string(REPLACE "|" ";" _w3_raw_fields "${_w3_raw_pair}")
      list(GET _w3_raw_fields 0 _w3_raw_target)
      list(GET _w3_raw_fields 1 _w3_raw_package)
      get_target_property(_w3_raw_definitions ${_w3_raw_target} INTERFACE_COMPILE_DEFINITIONS)
      if(NOT _w3_raw_definitions)
        set(_w3_raw_definitions "")
      endif()
      file(REAL_PATH "${${_w3_raw_package}_DIR}/../../.." _w3_raw_origin)
      file(REAL_PATH "${READER_GTK_RAW3_PREFIX}" _w3_raw_prefix)
      if(NOT _w3_raw_origin STREQUAL _w3_raw_prefix)
        message(FATAL_ERROR "GTK raw Wave 3 family origin differs: ${_w3_raw_package}")
      endif()
      if(_w3_raw_package STREQUAL "EXReaderAnnotationImport" OR _w3_raw_package STREQUAL "EXReaderJumpHistory" OR
         _w3_raw_package STREQUAL "EXReaderSyncView")
        if(NOT "EXR_READER_SELECTOR_BYTES_CANDIDATE=1" IN_LIST _w3_raw_definitions)
          message(FATAL_ERROR "GTK raw Wave 3 needs the raw0.2 family: ${_w3_raw_package}")
        endif()
      else()
        if("EXR_READER_SELECTOR_BYTES_CANDIDATE=1" IN_LIST _w3_raw_definitions)
          message(FATAL_ERROR "GTK raw Wave 3 refuses a raw-capability single-family package: ${_w3_raw_package}")
        endif()
      endif()
    endforeach()
    # Jump history keeps the real anchor version of every landing: an anchor3
    # wire is only ever produced by the fixed_page encoder, and a reflow or EPUB
    # landing keeps its v2 wire through the explicit public pure raw capture
    # candidate. Without that candidate a raw store cannot retain a v2 landing at
    # all, so refuse here instead of silently dropping history.
    get_target_property(_w3_raw_codec_definitions EXReaderReadingState::reader_reading_state_codec INTERFACE_COMPILE_DEFINITIONS)
    if(NOT "EXR_READER_PURE_CAPTURE_CANDIDATE=1" IN_LIST _w3_raw_codec_definitions)
      message(FATAL_ERROR "GTK raw Wave 3 history needs the installed reading-state 0.2.0 public pure raw capture candidate (EXR_READER_PURE_CAPTURE_CANDIDATE=ON)")
    endif()
  endif()
  target_compile_definitions(exreader-linux-reading PUBLIC EXR_READER_WAVE3=1)
  target_compile_definitions(exreader-linux PRIVATE EXR_READER_WAVE3_UI=1)
  if(EXR_READER_GTK_RAW3)
    target_compile_definitions(exreader-linux-reading PUBLIC EXR_READER_WAVE3_RAW3=1)
  endif()
  target_link_libraries(exreader-linux-reading PUBLIC
    EXReaderAnnotationImport::reader_annotation_import EXReaderFontLibrary::reader_font_library
    EXReaderOriginalExport::reader_original_export EXReaderJumpHistory::reader_jump_history
    EXReaderSyncView::reader_sync_view)
  if(EXR_LINUX_REVIEW_TESTS)
    if(EXR_READER_GTK_RAW3)
      # The raw family refuses the legacy exporter/importer files, so its owner
      # probe is its own driver; the original C10 driver stays untouched.
      add_executable(reader-gtk-wave3-raw-backend ../../../tests/reader_gtk_raw_wave3/backend.c)
      # The probe compiles the literal worker with the actual host definitions and
      # the actual owner libraries, so it reads the real history wires and the real
      # raw store. Same pattern as the retained raw owner probe.
      get_target_property(_w3_raw_owner_definitions exreader-linux-reading COMPILE_DEFINITIONS)
      get_target_property(_w3_raw_owner_links exreader-linux-reading LINK_LIBRARIES)
      target_compile_definitions(reader-gtk-wave3-raw-backend PRIVATE ${_w3_raw_owner_definitions}
        "REAL_READING_SOURCE=\"${CMAKE_CURRENT_LIST_DIR}/../../../examples/linux/reading.c\"")
      target_compile_options(reader-gtk-wave3-raw-backend PRIVATE -Wall -Wextra -Werror)
      target_link_libraries(reader-gtk-wave3-raw-backend PRIVATE exreader-linux-reading ${_w3_raw_owner_links}
        EXReaderAnnotationExport::reader_annotation_export reader_catalog_sdk reader_catalog_sqlite PkgConfig::GLIB)
    else()
      add_executable(reader-gtk-wave3-backend ../../../tests/reader_wave3_c10/backend.c)
      target_compile_options(reader-gtk-wave3-backend PRIVATE -Wall -Wextra -Werror)
      target_link_libraries(reader-gtk-wave3-backend PRIVATE exreader-linux-reading
        EXReaderAnnotationExport::reader_annotation_export reader_catalog_sdk reader_catalog_sqlite PkgConfig::GLIB)
    endif()
  endif()
endif()
