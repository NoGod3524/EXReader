# SPDX-License-Identifier: MIT
# GTK owner include (C10). Included once by desktop/CMakeLists.txt after the
# existing GTK targets; absent options preserve the old graph byte for byte.
#
# EXR_READER_GTK_WAVE3 adds the five Wave 3 tools to the compact native host:
# checked annotation import, local font library leases, original export, jump
# history and a read-only sync status. Every module comes from one installed
# prefix; the host copies no parser, store or SDK.
option(EXR_READER_GTK_WAVE3 "Enable native annotation import, fonts, original export, history and sync status" OFF)
set(READER_WAVE3_PREFIX "" CACHE PATH "Installed annotation import, font library, original export, jump history and sync status packages")
if(EXR_READER_GTK_WAVE3)
  if(NOT EXR_READER_BUILD_GTK OR NOT UNIX OR APPLE)
    message(FATAL_ERROR "GTK Wave 3 tools require the Linux GTK host")
  endif()
  if(NOT EXR_READER_GTK_COMPACT)
    message(FATAL_ERROR "GTK Wave 3 tools live in the compact More menu; enable EXR_READER_GTK_COMPACT")
  endif()
  if(NOT EXR_READER_GTK_ACCOUNT OR NOT EXR_READER_GTK_READING_RECORDS OR NOT EXR_READER_GTK_SEARCH OR NOT EXR_READER_GTK_NAVIGATION)
    message(FATAL_ERROR "GTK Wave 3 tools borrow the account, records, search and navigation owners")
  endif()
  if(EXR_READER_GTK_RAW3)
    message(FATAL_ERROR "GTK Wave 3 tools are validated on the legacy module families only")
  endif()
  if(NOT EXR_SDK_VERSION STREQUAL "3.41.0" OR NOT READER_WAVE3_PREFIX)
    message(FATAL_ERROR "GTK Wave 3 tools need SDK 3.41.0 and one installed module prefix")
  endif()
  list(PREPEND CMAKE_PREFIX_PATH "${READER_WAVE3_PREFIX}" "${EXR_SDK}")
  find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
  find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
  target_compile_definitions(exreader-linux-reading PUBLIC EXR_READER_WAVE3=1)
  target_compile_definitions(exreader-linux PRIVATE EXR_READER_WAVE3_UI=1)
  target_link_libraries(exreader-linux-reading PUBLIC
    EXReaderAnnotationImport::reader_annotation_import EXReaderFontLibrary::reader_font_library
    EXReaderOriginalExport::reader_original_export EXReaderJumpHistory::reader_jump_history
    EXReaderSyncView::reader_sync_view)
  if(EXR_LINUX_REVIEW_TESTS)
    find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
    add_executable(reader-gtk-wave3-backend ../../../tests/reader_wave3_c10/backend.c)
    target_compile_options(reader-gtk-wave3-backend PRIVATE -Wall -Wextra -Werror)
    target_link_libraries(reader-gtk-wave3-backend PRIVATE exreader-linux-reading
      EXReaderAnnotationExport::reader_annotation_export reader_catalog_sdk reader_catalog_sqlite PkgConfig::GLIB)
  endif()
endif()
