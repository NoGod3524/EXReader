# Opt-in without changing the root CMakeLists.txt or its baseline registrations:
# cmake -S . -B build/native -DCMAKE_PROJECT_INCLUDE=<absolute-path-to-this-file>
function(exr_docx_real_tests)
  if(NOT EXR_BUILD_TESTS OR NOT TARGET exreader OR TARGET exreader-docx-real-alloc-test)
    return()
  endif()
  find_package(Python3 REQUIRED COMPONENTS Interpreter)
  set(fixtures "${CMAKE_CURRENT_FUNCTION_LIST_DIR}")
  file(GLOB documents "${fixtures}/*.docx")
  list(LENGTH documents fixture_count)
  if(NOT fixture_count EQUAL 30)
    message(FATAL_ERROR "docx-real requires exactly 30 committed fixtures")
  endif()
  add_test(NAME native-docx-real-reproducible COMMAND "${Python3_EXECUTABLE}" "${fixtures}/generate.py" --check)
  foreach(document IN LISTS documents)
    get_filename_component(id "${document}" NAME_WE)
    foreach(mode noop edited)
      add_test(NAME native-docx-real-${id}-${mode} COMMAND "${Python3_EXECUTABLE}"
        "${fixtures}/run_matrix.py" --library "$<TARGET_FILE:exreader>" --case "${id}" --mode "${mode}")
    endforeach()
  endforeach()
  foreach(regression text-command paragraph-markers section-tail text-history text-alias text-validation text-transaction)
    add_test(NAME native-docx-real-${regression} COMMAND "${Python3_EXECUTABLE}"
      "${fixtures}/regressions.py" --library "$<TARGET_FILE:exreader>" "${regression}")
  endforeach()
  add_test(NAME native-docx-real-oracle-mutations COMMAND "${Python3_EXECUTABLE}" "${fixtures}/oracle_mutations.py")
  add_executable(exreader-docx-real-alloc-test "${fixtures}/test_text_alloc.c")
  target_include_directories(exreader-docx-real-alloc-test PRIVATE "${CMAKE_SOURCE_DIR}/include")
  target_compile_definitions(exreader-docx-real-alloc-test PRIVATE EXR_STATIC)
  add_test(NAME native-docx-real-text-allocation COMMAND exreader-docx-real-alloc-test)
  if(EXR_SANITIZE AND CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_C_COMPILER_ID STREQUAL "GNU")
    # These Python hosts load the instrumented SDK through ctypes. Load the same
    # compiler's runtime at process startup so ASan can intercept allocations.
    execute_process(COMMAND "${CMAKE_C_COMPILER}" -print-file-name=libasan.so
      OUTPUT_VARIABLE asan_runtime OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    if(NOT EXISTS "${asan_runtime}")
      message(FATAL_ERROR "DOCX ctypes tests require the compiler's shared ASan runtime")
    endif()
    get_property(docx_tests DIRECTORY PROPERTY TESTS)
    foreach(test IN LISTS docx_tests)
      # python ctypes 宿主一律预载 ASan；用家族前缀 + 排除 C 测试的写法，新加测试不用再改这里
      if(test MATCHES "^(native-docx-edit-|native-docx-(editor-e2e|realworld-matrix|real-)|native-pptx-|native-ppt-)"
          AND NOT test MATCHES "(reproducible|oracle-mutations|text-allocation|native-docx-edit-allocation|native-docx-edit-benchmark)$")
        set_property(TEST "${test}" APPEND PROPERTY ENVIRONMENT_MODIFICATION
          "LD_PRELOAD=path_list_prepend:${asan_runtime}" "PYTHONMALLOC=set:malloc")
      endif()
    endforeach()
  endif()
endfunction()
cmake_language(DEFER CALL exr_docx_real_tests)


