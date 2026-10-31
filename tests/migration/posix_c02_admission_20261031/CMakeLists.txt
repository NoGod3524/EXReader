cmake_minimum_required(VERSION 3.24)
project(PosixC02AdmissionCheck LANGUAGES C)
if(NOT PC02_PREFIX OR NOT WH_PREFIX)
 message(FATAL_ERROR "PC02_PREFIX and WH_PREFIX must name separate installed prefixes")
endif()
add_executable(posix-c02-admission-check pc02_test.c)
target_compile_features(posix-c02-admission-check PRIVATE c_std_11)
target_compile_options(posix-c02-admission-check PRIVATE -Wall -Wextra -Werror)
target_include_directories(posix-c02-admission-check PRIVATE
 "${PC02_PREFIX}/include/exreader-posix-c02-admission"
 "${WH_PREFIX}/include/exreader-migration-coordinator-hardening")
target_link_libraries(posix-c02-admission-check PRIVATE
 "${PC02_PREFIX}/lib/libexreader-posix-c02-admission.a"
 "${WH_PREFIX}/lib/libexreader-migration-coordinator-hardening.a")
target_compile_definitions(posix-c02-admission-check PRIVATE SOURCE_SHA="${SOURCE_SHA}")
