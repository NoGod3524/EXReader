# SPDX-License-Identifier: MIT
require 'xcodeproj'
require 'rbconfig'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
output, resources, tests, mode = ARGV
raise 'explicit mode' unless ['control', 'wave3'].include?(mode)
raise 'original generator failed' unless system(RbConfig.ruby, 'tests/apple_host/make_xcodeproj.rb', output, resources, tests)
project = Xcodeproj::Project.open(File.join(output, 'EXReaderHost.xcodeproj'))
project.targets.each do |target|
  next unless target.product_type == 'com.apple.product-type.application'
  target.build_configurations.each do |config|
    s = config.build_settings
    conditions = s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'].split(' ') + ['EXR_APPLE_HOST_REVIEW', 'EXR_APPLE_READING_REVIEW']
    if mode == 'wave3'
      conditions += ['EXR_APPLE_RAW3', 'EXR_APPLE_WAVE3']
      s['EXR_PRODUCTS_DIR'] = '$(SRCROOT)/raw-products'
      ['LIBRARY_SEARCH_PATHS'].each { |key| s[key].insert(1, '$(EXR_PRODUCTS_DIR)/lib') }
      ['HEADER_SEARCH_PATHS', 'SWIFT_INCLUDE_PATHS'].each { |key| s[key].insert(1, '$(EXR_PRODUCTS_DIR)/include/exreader-product'); s[key].insert(1, '$(EXR_PRODUCTS_DIR)/include') }
      s['SWIFT_INCLUDE_PATHS'] << File.join(Dir.pwd, 'apps/reader/apple-feature-integration/include')
      s['OTHER_SWIFT_FLAGS'] = ['$(inherited)', '-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1']
      s['OTHER_LDFLAGS'] += ['-lreader_annotation_import', '-lreader_annotation_export', '-lreader_font_library',
        '-lreader_original_export', '-lreader_jump_history', '-lreader_sync_view']
      # Preserve the original embed/check phase byte-for-byte. All resolution
      # remains in the dynamic SDK, using the existing owner wrappers.
    end
    s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = conditions.uniq.join(' ')
  end
end
project.save
