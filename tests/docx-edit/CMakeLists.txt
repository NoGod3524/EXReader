# SPDX-License-Identifier: MIT
# Like the other ctypes oracles, this needs a native, unsanitized shared SDK.
if(EXR_SANITIZE OR ANDROID OR CMAKE_CROSSCOMPILING OR NOT EXR_BUILD_SHARED_COMPAT)
  return()
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(EXR_DOCX_EDIT_TEST_LIBRARY "" CACHE FILEPATH
  "Override the editable DOCX SDK for pre-merge integration; default: this build's exreader")
set(EXR_DOCX_EDIT_VALIDATOR_DIR "${PROJECT_SOURCE_DIR}/tools/docx" CACHE PATH
  "Directory containing #117 verify_docx.py and roundtrip.py")
if(EXR_DOCX_EDIT_TEST_LIBRARY)
  set(docx_edit_library "${EXR_DOCX_EDIT_TEST_LIBRARY}")
else()
  set(docx_edit_library "$<TARGET_FILE:exreader>")
endif()
set(docx_edit_output "${PROJECT_BINARY_DIR}/docx-edit")
add_test(NAME native-docx-edit-fixtures COMMAND "${Python3_EXECUTABLE}"
  "${PROJECT_SOURCE_DIR}/tests/fixtures/docx-edit/generate.py" --check)
set_tests_properties(native-docx-edit-fixtures PROPERTIES
  FIXTURES_SETUP docx-edit-fixtures LABELS "docx-edit;e2e" TIMEOUT 60)
foreach(fixture plain heading table image notes sections)
  foreach(kind content structure properties)
    set(name native-docx-edit-e2e-${fixture}-${kind})
    add_test(NAME ${name} COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/run.py"
      --library "${docx_edit_library}" --validator-dir "${EXR_DOCX_EDIT_VALIDATOR_DIR}"
      --fixture ${fixture} --case ${kind} --output "${docx_edit_output}/${fixture}-${kind}")
    set_tests_properties(${name} PROPERTIES FIXTURES_REQUIRED docx-edit-fixtures
      LABELS "docx-edit;e2e" TIMEOUT 60)
  endforeach()
endforeach()
add_test(NAME native-docx-edit-e2e-table-negative COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/run.py" --library "${docx_edit_library}"
  --validator-dir "${EXR_DOCX_EDIT_VALIDATOR_DIR}" --negative-table
  --output "${docx_edit_output}/table-negative")
set_tests_properties(native-docx-edit-e2e-table-negative PROPERTIES
  FIXTURES_REQUIRED docx-edit-fixtures LABELS "docx-edit;e2e" TIMEOUT 90)
