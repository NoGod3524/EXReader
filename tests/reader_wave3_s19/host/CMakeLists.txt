# SPDX-License-Identifier: MIT
# S19 host: one product DSO that owns the five reviewed modules and the single
# product store provider, plus one real executable that loads it and shares the
# one installed shared SDK. Every package below is an installed package; nothing
# is added by source and no module or SDK target is rewritten.
cmake_minimum_required(VERSION 3.24)
project(S19Host LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(MSVC)
  set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  add_compile_options(/utf-8)
endif()

set(EXR_SDK "" CACHE PATH "Single installed SDK prefix")
set(EXR_SDK_VERSION "3.41.0" CACHE STRING "Exact installed SDK version")
set(EXR_STORE "" CACHE PATH "Installed product catalog prefix")
set(EXR_MODULE_PREFIXES "" CACHE STRING "Installed optional package prefixes")
if(EXR_SDK)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
endif()

find_package(EXReader ${EXR_SDK_VERSION} EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
foreach(_prefix IN LISTS EXR_MODULE_PREFIXES)
  list(PREPEND CMAKE_PREFIX_PATH "${_prefix}")
endforeach()
if(EXR_STORE)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_STORE}")
endif()
find_package(EXReaderProductCatalog 0.1.0 EXACT CONFIG REQUIRED
  PATHS "${EXR_STORE}" NO_DEFAULT_PATH)
find_package(EXReaderAnnotationImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderFontLibrary 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderOriginalExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderJumpHistory 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderSyncView 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderHostFeatureLink 1.0.0 EXACT CONFIG REQUIRED)

if(WIN32)
  set(_sdk_link static)
else()
  set(_sdk_link shared)
endif()
exr_reader_host_feature_link_declare(host_features
  SDK_PREFIX "${EXR_SDK}"
  SDK_VERSION "${EXR_SDK_VERSION}"
  SDK_LINK ${_sdk_link}
  STORE_PREFIX "${EXR_STORE}"
  PACKAGE_PREFIXES ${EXR_MODULE_PREFIXES})

if(WIN32)
  set(READER_METADATA_PREFIX "${EXR_STORE}" CACHE PATH "" FORCE)
  set(READER_ACCOUNT_PREFIX "${EXR_STORE}" CACHE PATH "" FORCE)
  add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../../../apps/reader/windows-account" windows-product)
  target_sources(EXReaderProduct PRIVATE features.cpp main.cpp)
  target_compile_definitions(EXReaderProduct PRIVATE EXR_S19_WINDOWS_FEATURES=1)
  exr_reader_host_feature_link_attach_windows_gui(EXReaderProduct host_features)
else()
add_library(reader_host_features SHARED features.cpp)
set_target_properties(reader_host_features PROPERTIES BUILD_WITH_INSTALL_RPATH ON)
exr_reader_host_feature_link_attach(reader_host_features host_features ROLE FEATURE_DSO)

add_executable(reader-host-probe main.cpp)
set_target_properties(reader-host-probe PROPERTIES BUILD_WITH_INSTALL_RPATH ON)
target_link_libraries(reader-host-probe PRIVATE ${CMAKE_DL_LIBS})
exr_reader_host_feature_link_attach(reader-host-probe host_features
  ROLE HOST_EXECUTABLE HOST_OF reader_host_features)
endif()
