# SPDX-License-Identifier: MIT
# Keep the original generator and its default OFF callers unchanged.
require 'xcodeproj'
require 'rbconfig'
require 'pathname'
output, resources, tests, mode = ARGV
raise 'raw or legacy project required' unless ['raw', 'legacy'].include?(mode)
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
root = Dir.pwd
ok = system({'EXR_APPLE_SDK_VERSION' => '3.41.0', 'EXR_APPLE_PAGE_THEME' => 'ON'},
  RbConfig.ruby, File.join(root, 'tests/apple_host/make_xcodeproj.rb'), output, resources, tests)
raise 'original project generation failed' unless ok
project = Xcodeproj::Project.open(File.join(output, 'EXReaderHost.xcodeproj'))
project.targets.each do |target|
  next unless target.product_type == 'com.apple.product-type.application'
  target.build_configurations.each do |config|
    settings = config.build_settings
    conditions = settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'].split(' ')
    conditions += ['EXR_APPLE_RAW3_REVIEW', 'EXR_APPLE_HOST_REVIEW', 'EXR_APPLE_READING_REVIEW']
    if mode == 'raw'
      conditions << 'EXR_APPLE_RAW3'
      settings['EXR_PRODUCTS_DIR'] = '$(SRCROOT)/raw-products'
      settings['LIBRARY_SEARCH_PATHS'].insert(1, '$(EXR_PRODUCTS_DIR)/lib')
      settings['HEADER_SEARCH_PATHS'].insert(1, '$(EXR_PRODUCTS_DIR)/include/exreader-product')
      settings['HEADER_SEARCH_PATHS'].insert(1, '$(EXR_PRODUCTS_DIR)/include')
      settings['SWIFT_INCLUDE_PATHS'].insert(1, '$(EXR_PRODUCTS_DIR)/include/exreader-product')
      settings['SWIFT_INCLUDE_PATHS'].insert(1, '$(EXR_PRODUCTS_DIR)/include')
      settings['OTHER_SWIFT_FLAGS'] = ['$(inherited)', '-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1']
    end
    settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = conditions.uniq.join(' ')
    plist = File.expand_path(settings['INFOPLIST_FILE'], output)
    info = Xcodeproj::Plist.read_from_path(plist)
    info['EXRRawSelectorEnabled'] = mode == 'raw'
    info['EXRRawReviewEnabled'] = true
    Xcodeproj::Plist.write_to_path(info, plist)
  end
end
project.save
