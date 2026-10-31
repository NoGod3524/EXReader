cmake_minimum_required(VERSION 3.16)
project(CoordinatorNativeJournal LANGUAGES C)
if(NOT WIN32)
  message(FATAL_ERROR "This adapter requires Windows and local NTFS")
endif()
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_library(exreader-coordinator-native STATIC src/wh3_win.c src/wh3_registry.c)
target_link_libraries(exreader-coordinator-native PUBLIC advapi32)
target_compile_options(exreader-coordinator-native PRIVATE /utf-8 /W4 /WX)
target_compile_definitions(exreader-coordinator-native PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602)
target_include_directories(exreader-coordinator-native PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/exreader-coordinator-native>
  "${WH_PREFIX}/include/exreader-coordinator-cas"
  "${WH_PREFIX}/include/exreader-migration-coordinator-hardening")
set_target_properties(exreader-coordinator-native PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
install(TARGETS exreader-coordinator-native ARCHIVE DESTINATION lib)
install(FILES include/exr_wh3_win.h DESTINATION include/exreader-coordinator-native)
