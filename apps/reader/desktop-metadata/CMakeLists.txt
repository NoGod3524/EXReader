# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderDesktopMetadata VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
find_package(EXReaderCommands 0.1.0 EXACT CONFIG REQUIRED)
add_library(reader_desktop_metadata STATIC src/metadata.cpp)
target_include_directories(reader_desktop_metadata PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_desktop_metadata PUBLIC EXReaderCommands::reader_commands
  PRIVATE EXReaderProductCatalog::reader_catalog)
if(MSVC)
  target_compile_options(reader_desktop_metadata PRIVATE /W4 /WX)
else()
  target_compile_options(reader_desktop_metadata PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_desktop_metadata EXPORT EXReaderDesktopMetadataTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_metadata.h DESTINATION include)
install(EXPORT EXReaderDesktopMetadataTargets NAMESPACE EXReaderDesktopMetadata:: DESTINATION lib/cmake/EXReaderDesktopMetadata)
configure_package_config_file(EXReaderDesktopMetadataConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopMetadataConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderDesktopMetadata)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopMetadataConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopMetadataConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderDesktopMetadataConfigVersion.cmake" DESTINATION lib/cmake/EXReaderDesktopMetadata)
