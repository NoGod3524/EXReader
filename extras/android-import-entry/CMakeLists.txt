# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderAndroidImportEntry VERSION 0.1.0 LANGUAGES C)
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()
find_package(EXReader CONFIG REQUIRED COMPONENTS library)
find_package(EXReaderSideload CONFIG REQUIRED)
add_library(exr_android_import_entry STATIC src/entry.c)
target_include_directories(exr_android_import_entry PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
target_link_libraries(exr_android_import_entry PUBLIC EXReaderSideload::exr_sideload)
set_target_properties(exr_android_import_entry PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON
  POSITION_INDEPENDENT_CODE ON)
install(TARGETS exr_android_import_entry EXPORT EXReaderAndroidImportEntryTargets ARCHIVE DESTINATION lib)
install(FILES include/exr_android_import_entry.h DESTINATION include)
install(DIRECTORY sample DESTINATION share/exreader-android-import-entry)
install(EXPORT EXReaderAndroidImportEntryTargets NAMESPACE EXReaderAndroidImportEntry:: DESTINATION lib/cmake/EXReaderAndroidImportEntry)
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAndroidImportEntryConfig.cmake"
  "include(CMakeFindDependencyMacro)\nfind_dependency(EXReader CONFIG COMPONENTS library)\nfind_dependency(EXReaderSideload CONFIG)\ninclude(\"\${CMAKE_CURRENT_LIST_DIR}/EXReaderAndroidImportEntryTargets.cmake\")\nget_filename_component(EXR_ANDROID_IMPORT_ENTRY_SAMPLE_DIR \"\${CMAKE_CURRENT_LIST_DIR}/../../../share/exreader-android-import-entry/sample\" ABSOLUTE)\n")
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderAndroidImportEntryConfig.cmake" DESTINATION lib/cmake/EXReaderAndroidImportEntry)
