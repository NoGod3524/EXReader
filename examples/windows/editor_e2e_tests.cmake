# SPDX-License-Identifier: MIT
# cmake -S . -B build/l12 -DCMAKE_PROJECT_EXReader_INCLUDE=<absolute path to this file>
# cmake --build build/l12 --target check_shell_editor_e2e
# ctest --test-dir build/l12 -R ^native-shell-editor-e2e$ -V
if(WIN32 AND PROJECT_NAME STREQUAL "EXReader")
  enable_language(CXX)
  function(exr_add_editor_e2e)
    if(NOT EXR_BUILD_TESTS)
      return()
    endif()
    add_executable(check_shell_editor_e2e
      examples/windows/check_shell_editor_e2e.c
      examples/windows/shell_d2d.cpp
      examples/windows/shell_epub.cpp
      examples/windows/shell_speech.cpp)
    target_compile_features(check_shell_editor_e2e PRIVATE cxx_std_17)
    target_compile_definitions(check_shell_editor_e2e PRIVATE EXR_READER_WINDOWS_SHELL=1
      EXR_E2E_FIXTURE="${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/docx-real/codex/05-table-multi-paragraph.docx")
    target_include_directories(check_shell_editor_e2e PRIVATE include)
    target_link_libraries(check_shell_editor_e2e PRIVATE exreader miniz expat d2d1 dwrite
      gdi32 comdlg32 shell32 ole32 oleaut32 uuid uiautomationcore advapi32 winhttp ws2_32 crypt32)
    if(MSVC)
      target_compile_options(check_shell_editor_e2e PRIVATE /utf-8)
    else()
      target_link_libraries(check_shell_editor_e2e PRIVATE m)
    endif()
    add_test(NAME native-shell-editor-e2e COMMAND check_shell_editor_e2e)
    set_tests_properties(native-shell-editor-e2e PROPERTIES TIMEOUT 90 LABELS "headless;editor;docx")
  endfunction()
  cmake_language(DEFER CALL exr_add_editor_e2e)
endif()
