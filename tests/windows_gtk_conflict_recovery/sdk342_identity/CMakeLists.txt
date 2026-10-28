cmake_minimum_required(VERSION 3.24)
project(InstalledSDK342Identity LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
set(EXR_SDK "" CACHE PATH "Actual installed SDK 3.42 prefix")
find_package(EXReader 3.42.0 EXACT CONFIG REQUIRED COMPONENTS core library
  PATHS "${EXR_SDK}" NO_DEFAULT_PATH)
add_executable(sdk342-identity main.c)
target_link_libraries(sdk342-identity PRIVATE EXReader::exr_library EXReader::exr_core)
if(MSVC)
  target_link_options(sdk342-identity PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/sdk342-identity.map")
else()
  target_link_options(sdk342-identity PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/sdk342-identity.map")
endif()
# Frozen SDK core is an installed INTERFACE facade over its render archive.
# Keep linking the public core target; authenticate the real facade/backing file.
get_target_property(_core_type EXReader::exr_core TYPE)
get_target_property(_core_links EXReader::exr_core INTERFACE_LINK_LIBRARIES)
get_target_property(_render_type EXReader::exr_render TYPE)
if(NOT _core_type STREQUAL "INTERFACE_LIBRARY" OR
   NOT _core_links STREQUAL "EXReader::exr_render" OR
   NOT _render_type STREQUAL "STATIC_LIBRARY")
  message(FATAL_ERROR "Unexpected installed public core facade or render archive")
endif()
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/target-properties.txt"
  "core_type=${_core_type}\ncore_links=${_core_links}\nrender_type=${_render_type}\ncore_component_version=${EXReader_core_VERSION}\nlibrary_component_version=${EXReader_library_VERSION}\n")
file(GENERATE OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/linked-sdk.txt"
  CONTENT "${EXReader_DIR}\n$<TARGET_FILE:EXReader::exr_render>\n$<TARGET_FILE:EXReader::exr_library>\n")
