cmake_minimum_required(VERSION 3.24)
project(EXReaderPosixC02Admission LANGUAGES C)
if(WIN32)
  message(FATAL_ERROR "This local admission adapter requires native POSIX")
endif()
if(NOT WH_PREFIX)
  message(FATAL_ERROR "WH_PREFIX must name the installed frozen ABI2 coordinator prefix")
endif()
add_library(exreader-posix-c02-admission STATIC
 src/pc02.c src/pc02_repair_scan.c src/pc02_repair_store.c)
target_compile_features(exreader-posix-c02-admission PUBLIC c_std_11)
target_compile_options(exreader-posix-c02-admission PRIVATE -Wall -Wextra -Werror)
target_include_directories(exreader-posix-c02-admission PUBLIC
 $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
 $<INSTALL_INTERFACE:include/exreader-posix-c02-admission>
 PRIVATE "${WH_PREFIX}/include/exreader-migration-coordinator-hardening")
target_link_libraries(exreader-posix-c02-admission PUBLIC "${WH_PREFIX}/lib/libexreader-migration-coordinator-hardening.a")
install(TARGETS exreader-posix-c02-admission ARCHIVE DESTINATION lib)
install(FILES include/exr_pc02.h include/exr_pc02_repair_scan.h
 include/exr_pc02_repair_store.h DESTINATION include/exreader-posix-c02-admission)
