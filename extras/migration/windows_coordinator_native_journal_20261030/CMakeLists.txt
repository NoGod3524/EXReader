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

option(WH3_BUILD_SDK_TOOL "Build the actual SDK admission command" OFF)
if(WH3_BUILD_SDK_TOOL)
  enable_language(CXX)
  list(PREPEND CMAKE_PREFIX_PATH "${EXR_SDK}")
  find_package(EXReader 3.42.0 EXACT CONFIG REQUIRED COMPONENTS core library)
  add_executable(exreader-c02-admission tools/wh3_admission_main.c)
  target_compile_options(exreader-c02-admission PRIVATE /utf-8 /W4 /WX)
  target_compile_definitions(exreader-c02-admission PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602)
  target_link_libraries(exreader-c02-admission PRIVATE exreader-coordinator-native
    "${WH_PREFIX}/lib/exreader-coordinator-cas.lib"
    "${WH_PREFIX}/lib/exreader-migration-coordinator-hardening.lib"
    EXReader::exr_library)
  set_target_properties(exreader-c02-admission PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON LINKER_LANGUAGE CXX)
  install(TARGETS exreader-c02-admission RUNTIME DESTINATION bin)
endif()

if(WH3_BUILD_SDK_TOOL)
  include(FetchContent)
  FetchContent_Declare(c02_sqlite_header
    URL "https://www.sqlite.org/2026/sqlite-amalgamation-3540000.zip"
    URL_HASH SHA256=68e913b0fe8ec6b4e5f391c594a28872884e80d6cd042a1e50c957be46b5aa4d)
  FetchContent_MakeAvailable(c02_sqlite_header)
  execute_process(COMMAND git rev-parse HEAD WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
    OUTPUT_VARIABLE WH3_BUILD_SOURCE OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
  set(WH3_BUILD_RUN "$ENV{GITHUB_RUN_ID}")
  set(WH3_BUILD_ATTEMPT "$ENV{GITHUB_RUN_ATTEMPT}")
  if(NOT WH3_BUILD_RUN)
    set(WH3_BUILD_RUN "0")
    set(WH3_BUILD_ATTEMPT "0")
  endif()
  set(provider_sources tools/wh3_migrate_main.c tools/wh3_transform.c tools/wh3_transform.h
    tools/wh3_build.h.in CMakeLists.txt src/wh3_win.c src/wh3_registry.c include/exr_wh3_win.h
    ../src/lm_main.c ../src/lm_ledger.h ../src/lm.h ../src/lm_pack.c ../src/lm_util.c
    ../src/lm_mirror.c ../src/lm_mirror.h
    ../windows_coordinator_cas_20261030/src/wh3_core.c
    ../windows_coordinator_hardening_20261030/src/wh_core.c
    ../windows_coordinator_hardening_20261030/src/wh_digest.c
    ../windows_coordinator_hardening_20261030/include/exr_wh.h
    ../windows_coordinator_cas_20261030/include/exr_wh3.h)
  set(provider_material "C02-SDK-8357eafa28423a7ab93ba08b823af80f01ad1505\n")
  foreach(source IN LISTS provider_sources)
    file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${source}" digest)
    string(APPEND provider_material "${source}=${digest}\n")
  endforeach()
  string(SHA256 WH3_PROVIDER_SHA "${provider_material}")
  file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/wh3-provider-sources.txt" "${provider_material}")
  configure_file(tools/wh3_build.h.in wh3_build.h @ONLY)
  foreach(tool exreader-c02-migrate exreader-c02-migrate-test)
    add_executable(${tool} tools/wh3_migrate_main.c tools/wh3_transform.c
      ../src/lm_pack.c ../src/lm_util.c ../src/lm_mirror.c)
    target_include_directories(${tool} PRIVATE "${CMAKE_CURRENT_BINARY_DIR}" "${c02_sqlite_header_SOURCE_DIR}")
    target_compile_options(${tool} PRIVATE /utf-8 /W3)
    target_compile_definitions(${tool} PRIVATE _CRT_SECURE_NO_WARNINGS _WIN32_WINNT=0x0602 EXR_MIGRATION_TX_CANDIDATE=1)
    target_link_libraries(${tool} PRIVATE exreader-coordinator-native
      "${WH_PREFIX}/lib/exreader-coordinator-cas.lib"
      "${WH_PREFIX}/lib/exreader-migration-coordinator-hardening.lib"
      EXReader::exr_library psapi)
    set_target_properties(${tool} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON LINKER_LANGUAGE CXX)
  endforeach()
  target_compile_definitions(exreader-c02-migrate-test PRIVATE WH3_MIGRATION_TEST_CONTROLS=1)
  install(TARGETS exreader-c02-migrate RUNTIME DESTINATION bin)
endif()
