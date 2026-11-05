# Private Windows observation engine; no migration admission.
if(NOT WIN32)
  message(FATAL_ERROR "Windows observation engine requires native Windows")
endif()
if(NOT EXR_WINDOWS_ENGINE_SOURCE MATCHES "^[0-9a-f]+$")
  message(FATAL_ERROR "Pass the full source SHA in EXR_WINDOWS_ENGINE_SOURCE")
endif()
string(LENGTH "${EXR_WINDOWS_ENGINE_SOURCE}" _source_length)
if(NOT _source_length EQUAL 40)
  message(FATAL_ERROR "Source SHA must be 40 lowercase hex bytes")
endif()
add_library(exreader-migration-windows-engine STATIC engine.c protocol.c
 ../src/lm_recovery_win32_platform.c ../src/lm_util.c)
target_include_directories(exreader-migration-windows-engine PUBLIC
 $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
 $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../src>
 $<INSTALL_INTERFACE:include/exreader-migration-windows-engine>)
target_compile_definitions(exreader-migration-windows-engine PRIVATE
 LM_WE_SOURCE="${EXR_WINDOWS_ENGINE_SOURCE}" _WIN32_WINNT=0x0A00)
target_link_libraries(exreader-migration-windows-engine PUBLIC EXReader::exr_library advapi32 psapi)
set_target_properties(exreader-migration-windows-engine PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED ON)
add_executable(exreader-migration-windows-observer observer.c)
target_compile_definitions(exreader-migration-windows-observer PRIVATE
 LM_WE_SOURCE="${EXR_WINDOWS_ENGINE_SOURCE}" _WIN32_WINNT=0x0A00)
target_link_libraries(exreader-migration-windows-observer PRIVATE exreader-migration-windows-engine)
target_link_options(exreader-migration-windows-observer PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/observer-provider.map")
install(TARGETS exreader-migration-windows-engine ARCHIVE DESTINATION lib)
install(TARGETS exreader-migration-windows-observer RUNTIME DESTINATION bin)
install(FILES lm_win_engine.h ../src/lm_recovery_win32_platform.h ../src/lm.h
 DESTINATION include/exreader-migration-windows-engine)
