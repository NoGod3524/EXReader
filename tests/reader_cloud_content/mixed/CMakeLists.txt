cmake_minimum_required(VERSION 3.24)
project(reject_mixed_cloud LANGUAGES C CXX)
find_package(EXReaderCloudImport 0.1.0 EXACT CONFIG REQUIRED)
find_package(EXReaderCloudImportContentBound 0.1.0 EXACT CONFIG REQUIRED)
add_executable(mixed main.c)
target_link_libraries(mixed PRIVATE EXReaderCloudImport::reader_cloud_import
  EXReaderCloudImportContentBound::reader_cloud_import_content_bound)
