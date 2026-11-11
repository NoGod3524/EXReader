# Capture the actual checkout, generated compile settings and installed bytes.
# Kept in the install path so existing SDK packaging jobs carry provenance.
option(EXR_BUILD_MANIFEST "Install SDK build provenance" ON)
if(NOT EXR_BUILD_MANIFEST OR NOT EXR_BUILD_SHARED_COMPAT)
  return()
endif()
find_package(Python3 REQUIRED COMPONENTS Interpreter)
if(EXR_BUILD_TESTS)
  add_test(NAME native-build-manifest COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/tools/crossbuild/test_manifest.py")
endif()
set(manifest_dir "${CMAKE_CURRENT_BINARY_DIR}/exr-manifest")
file(MAKE_DIRECTORY "${manifest_dir}")
execute_process(COMMAND "${Python3_EXECUTABLE}"
  "${CMAKE_CURRENT_SOURCE_DIR}/tools/crossbuild/manifest.py" snapshot
  --source "${CMAKE_CURRENT_SOURCE_DIR}" --out "${manifest_dir}/source.json"
  COMMAND_ERROR_IS_FATAL ANY)

function(exr_manifest_value key value)
  string(REPLACE "\\" "\\\\" value "${value}")
  string(REPLACE "\"" "\\\"" value "${value}")
  string(REPLACE "\n" "\\n" value "${value}")
  string(REPLACE "\r" "\\r" value "${value}")
  string(REPLACE "\t" "\\t" value "${value}")
  string(APPEND manifest_json "\"${key}\":\"${value}\",\n")
  set(manifest_json "${manifest_json}" PARENT_SCOPE)
endfunction()
set(manifest_json "{\n")
foreach(variable CMAKE_VERSION CMAKE_C_COMPILER CMAKE_C_COMPILER_ID
    CMAKE_C_COMPILER_VERSION CMAKE_GENERATOR CMAKE_SYSTEM_NAME
    CMAKE_SYSTEM_PROCESSOR CMAKE_OSX_ARCHITECTURES CMAKE_OSX_SYSROOT
    CMAKE_OSX_DEPLOYMENT_TARGET CMAKE_ANDROID_ARCH_ABI CMAKE_SYSTEM_VERSION
    CMAKE_POSITION_INDEPENDENT_CODE CMAKE_C_STANDARD CMAKE_MSVC_RUNTIME_LIBRARY
    CMAKE_C_FLAGS CMAKE_C_FLAGS_RELEASE CMAKE_C_FLAGS_DEBUG
    CMAKE_C_FLAGS_RELWITHDEBINFO CMAKE_C_FLAGS_MINSIZEREL)
  exr_manifest_value("${variable}" "${${variable}}")
endforeach()
get_cmake_property(manifest_variables VARIABLES)
foreach(variable IN LISTS manifest_variables)
  if(variable MATCHES "^EXR_(BUILD_|ENABLE_|SANITIZE$)")
    exr_manifest_value("${variable}" "${${variable}}")
  endif()
endforeach()
foreach(dependency expat freetype miniz zlib)
  exr_manifest_value("${dependency}_SOURCE_DIR" "${${dependency}_SOURCE_DIR}")
endforeach()
foreach(layer IN LISTS exr_layers)
  foreach(property COMPILE_DEFINITIONS COMPILE_OPTIONS POSITION_INDEPENDENT_CODE)
    # Generator expressions expand after JSON escaping. Definitions can contain
    # quotes (MBEDTLS_CONFIG_FILE), so preserve their expanded values as text.
    file(GENERATE OUTPUT "${manifest_dir}/targets-$<CONFIG>/${layer}.${property}.txt"
      CONTENT "$<TARGET_PROPERTY:exr_${layer}_objects,${property}>")
  endforeach()
endforeach()
exr_manifest_value("target_properties_directory" "${manifest_dir}/targets-$<CONFIG>")
exr_manifest_value("configuration" "$<CONFIG>")
string(APPEND manifest_json "\"schema_version\":1\n}\n")
file(GENERATE OUTPUT "${manifest_dir}/settings-$<CONFIG>.json" CONTENT "${manifest_json}")
if(WIN32)
  set(manifest_library_dir bin)
else()
  set(manifest_library_dir lib)
endif()
install(CODE "
  execute_process(COMMAND \"${Python3_EXECUTABLE}\"
    \"${CMAKE_CURRENT_SOURCE_DIR}/tools/crossbuild/manifest.py\" capture
    --source \"${CMAKE_CURRENT_SOURCE_DIR}\"
    --build \"${CMAKE_CURRENT_BINARY_DIR}\"
    --settings \"${manifest_dir}/settings-$<CONFIG>.json\"
    --snapshot \"${manifest_dir}/source.json\"
    --binary \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/${manifest_library_dir}/$<TARGET_FILE_NAME:exreader>\"
    --out \"\$ENV{DESTDIR}\${CMAKE_INSTALL_PREFIX}/share/exreader/validation\"
    COMMAND_ERROR_IS_FATAL ANY)
")
