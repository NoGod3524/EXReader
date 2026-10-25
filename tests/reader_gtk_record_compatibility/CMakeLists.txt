cmake_minimum_required(VERSION 3.24)
project(GTKRecordCompatibility LANGUAGES C CXX)
# The real owner is a subdirectory. Its imported package targets must also be
# visible to this parent-directory source probe, without editing that owner.
set(CMAKE_FIND_PACKAGE_TARGETS_GLOBAL TRUE)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GLIB REQUIRED IMPORTED_TARGET GLOBAL glib-2.0)
if(NOT HOST_SOURCE OR NOT EXR_SDK OR NOT MODULE_PREFIX)
  message(FATAL_ERROR "Explicit owner source and two installed prefixes required")
endif()
set(READER_METADATA_PREFIX "${MODULE_PREFIX}" CACHE PATH "" FORCE)
set(READER_ACCOUNT_PREFIX "${MODULE_PREFIX}" CACHE PATH "" FORCE)
set(READER_READING_RECORDS_PREFIX "${MODULE_PREFIX}" CACHE PATH "" FORCE)
set(EXR_READER_BUILD_GTK ON CACHE BOOL "" FORCE)
set(EXR_READER_GTK_ACCOUNT ON CACHE BOOL "" FORCE)
set(EXR_READER_GTK_READING_RECORDS ON CACHE BOOL "" FORCE)
set(EXR_LINUX_REVIEW_TESTS ON CACHE BOOL "" FORCE)
set(EXR_READER_FIXTURES "${HOST_SOURCE}/tests/fixtures" CACHE PATH "" FORCE)
add_subdirectory("${HOST_SOURCE}/apps/reader/desktop" actual-owner)
get_target_property(owner_definitions exreader-linux-reading COMPILE_DEFINITIONS)
get_target_property(owner_links exreader-linux-reading LINK_LIBRARIES)
add_executable(gtk-record-compatibility probe.c)
target_compile_definitions(gtk-record-compatibility PRIVATE ${owner_definitions}
  "REAL_READING_SOURCE=\"${HOST_SOURCE}/examples/linux/reading.c\"")
target_link_libraries(gtk-record-compatibility PRIVATE exreader-linux-reading
  ${owner_links} reader_catalog_sdk reader_catalog_sqlite PkgConfig::GLIB)
target_compile_options(gtk-record-compatibility PRIVATE -Wall -Wextra -Werror)
target_link_options(gtk-record-compatibility PRIVATE
  "-Wl,--wrap=reader_rc_apply" "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/owner.map")
