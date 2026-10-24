# Appended to an Actions-side COPY of the immutable G08 consumer CMakeLists.
find_package(EXReaderThumbnails 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderReadingCommands 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationView 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderAnnotationExport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderLocalDownloads 0.1.0 EXACT CONFIG REQUIRED)
set(g1_targets
  EXReaderThumbnails::reader_thumbnails
  EXReaderReadingCommands::reader_reading_commands
  EXReaderAnnotationView::reader_annotation_view
  EXReaderAnnotationExport::reader_annotation_export
  EXReaderLocalDownloads::reader_local_downloads)
set(g1_headers reader_thumbnails.h reader_reading_commands.h reader_annotation_view.h
  reader_annotation_export.h reader_local_downloads.h)
foreach(i RANGE 0 4)
  list(GET g1_targets ${i} owner)
  list(GET g1_headers ${i} header)
  exr_header_probe(${owner} ${header} C)
  exr_header_probe(${owner} ${header} CXX)
endforeach()
add_executable(g1-chain g1_chain.cpp)
target_link_libraries(g1-chain PRIVATE ${g1_targets} ${EXR_COMPOSED_LIBRARIES})
add_executable(g1-codec-only codec_scope.c)
set_target_properties(g1-codec-only PROPERTIES LINKER_LANGUAGE CXX)
target_link_libraries(g1-codec-only PRIVATE
  EXReaderReadingCommands::reader_reading_commands
  EXReaderAnnotationView::reader_annotation_view
  EXReaderAnnotationExport::reader_annotation_export)
if(MSVC)
  target_link_options(g1-chain PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/g1-chain.map")
  target_link_options(g1-codec-only PRIVATE "/MAP:${CMAKE_CURRENT_BINARY_DIR}/g1-codec.map")
elseif(APPLE)
  target_link_options(g1-chain PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/g1-chain.map")
  target_link_options(g1-codec-only PRIVATE "-Wl,-map,${CMAKE_CURRENT_BINARY_DIR}/g1-codec.map")
else()
  target_link_options(g1-chain PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/g1-chain.map")
  target_link_options(g1-codec-only PRIVATE "-Wl,-Map,${CMAKE_CURRENT_BINARY_DIR}/g1-codec.map")
endif()
