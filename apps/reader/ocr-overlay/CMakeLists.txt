# SPDX-License-Identifier: MIT
cmake_minimum_required(VERSION 3.24)
project(EXReaderOCROverlay VERSION 0.1.0 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()
# Installed public packages only: the frozen SDK core component and the separate
# optional OCR adapter. No SDK private header, no second Tesseract build, no
# product catalog and no host UI toolkit is used or linked here.
find_package(EXReader 3.40.0 EXACT CONFIG REQUIRED COMPONENTS core)
find_package(EXReaderOCR CONFIG REQUIRED)
add_library(reader_ocr_overlay STATIC src/ocr_overlay.cpp)
target_include_directories(reader_ocr_overlay PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include> $<INSTALL_INTERFACE:include>)
target_link_libraries(reader_ocr_overlay PUBLIC EXReader::exr_core PRIVATE EXReaderOCR::exreader_ocr)
if(MSVC)
  target_compile_options(reader_ocr_overlay PRIVATE /W4 /WX)
else()
  target_compile_options(reader_ocr_overlay PRIVATE -Wall -Wextra -Werror)
endif()
include(CMakePackageConfigHelpers)
install(TARGETS reader_ocr_overlay EXPORT EXReaderOCROverlayTargets ARCHIVE DESTINATION lib)
install(FILES include/reader_ocr_overlay.h DESTINATION include)
install(EXPORT EXReaderOCROverlayTargets NAMESPACE EXReaderOCROverlay:: DESTINATION lib/cmake/EXReaderOCROverlay)
configure_package_config_file(EXReaderOCROverlayConfig.cmake.in "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOCROverlayConfig.cmake"
  INSTALL_DESTINATION lib/cmake/EXReaderOCROverlay)
write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/EXReaderOCROverlayConfigVersion.cmake"
  VERSION ${PROJECT_VERSION} COMPATIBILITY SameMinorVersion)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOCROverlayConfig.cmake"
  "${CMAKE_CURRENT_BINARY_DIR}/EXReaderOCROverlayConfigVersion.cmake" DESTINATION lib/cmake/EXReaderOCROverlay)
