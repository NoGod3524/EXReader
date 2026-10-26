# SPDX-License-Identifier: MIT
require 'xcodeproj'
require 'rbconfig'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
output, resources, tests, mode = ARGV
raise 'explicit mode' unless ['base', 'control', 'wave3'].include?(mode)
raise 'original generator failed' unless system(RbConfig.ruby, 'tests/apple_host/make_xcodeproj.rb', output, resources, tests)
project = Xcodeproj::Project.open(File.join(output, 'EXReaderHost.xcodeproj'))
project.targets.each do |target|
  next unless target.product_type == 'com.apple.product-type.application'
  target.build_configurations.each do |config|
    s = config.build_settings
    conditions = s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'].split(' ') -
      ['EXR_APPLE_IMPORT_REVIEW', 'EXR_APPLE_READING_REVIEW']
    conditions << 'EXR_APPLE_HOST_REVIEW'
    conditions << 'EXR_APPLE_READING_REVIEW' if mode == 'control'
    conditions += ['EXR_APPLE_RAW3', 'EXR_APPLE_WAVE3']
    s['EXR_PRODUCTS_DIR'] = '$(SRCROOT)/raw-products'
    # xcodeproj reads some list-valued settings back as String. Assign complete
    # lists so String#insert/#<< cannot concatenate unrelated include paths.
    s['LIBRARY_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/lib', '$(EXR_SDK_DIR)/lib']
    s['HEADER_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/include',
      '$(EXR_PRODUCTS_DIR)/include/exreader-product', '$(EXR_SDK_DIR)/include',
      '$(EXR_SDK_DIR)/include/exreader-product']
    s['SWIFT_INCLUDE_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/include',
      '$(EXR_PRODUCTS_DIR)/include/exreader-product', '$(EXR_SDK_DIR)/include',
      '$(EXR_SDK_DIR)/include/exreader-product', File.join(Dir.pwd, 'examples/apple/product'),
      File.join(Dir.pwd, 'apps/reader/apple-feature-integration/include')]
    s['OTHER_SWIFT_FLAGS'] = ['$(inherited)', '-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1',
      '-Xcc', '-DEXR_APPLE_WAVE3=1']
    s['OTHER_LDFLAGS'] += ['-lreader_annotation_import', '-lreader_annotation_export', '-lreader_font_library',
      '-lreader_original_export', '-lreader_jump_history', '-lreader_sync_view']
    # Preserve the original embed/check phase byte-for-byte. All resolution
    # remains in the dynamic SDK, using the existing owner wrappers.
    s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = conditions.uniq.join(' ')
  end
end
project.save
