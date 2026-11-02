# SPDX-License-Identifier: MIT
# Links the retained G16 accessibility project (tests/reader_a11y_apple) against
# the installed same-source product, the way tests/apple_host/make_xcodeproj.rb
# and tests/reader_team24_apple/make_project.rb link the host: the audited app is
# the current product host, not an SDK-only build. G16's targets, schemes, test
# sources and compilation conditions are kept; only product settings are added.
require 'xcodeproj'
require 'json'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
project_path, products, option = ARGV
production = option == '--production'
raise 'usage: apple_product_overlay.rb <project> <products-prefix> [--production]' unless project_path && products && (ARGV.length == 2 || (ARGV.length == 3 && production))
production_records = []
project = Xcodeproj::Project.open(project_path)
root = Dir.pwd
project.targets.each do |target|
  next unless target.product_type == 'com.apple.product-type.application'
  target.build_configurations.each do |config|
    s = config.build_settings
    s['EXR_PRODUCTS_DIR'] = File.expand_path(products)
    s['ENABLE_DEBUG_DYLIB'] = 'NO'
    s['CLANG_ENABLE_MODULES'] = 'YES'
    s['LIBRARY_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/lib', '$(EXR_SDK_DIR)/lib']
    s['HEADER_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/include',
      '$(EXR_PRODUCTS_DIR)/include/exreader-product', '$(EXR_SDK_DIR)/include', '$(EXR_SDK_DIR)/include/exreader-product']
    s['SWIFT_INCLUDE_PATHS'] = ['$(inherited)', '$(EXR_PRODUCTS_DIR)/include',
      '$(EXR_PRODUCTS_DIR)/include/exreader-product', '$(EXR_SDK_DIR)/include', '$(EXR_SDK_DIR)/include/exreader-product',
      File.join(root, 'examples/apple/product'), File.join(root, 'apps/reader/apple-feature-integration/include')]
    s['OTHER_SWIFT_FLAGS'] = ['$(inherited)', '-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1', '-Xcc', '-DEXR_APPLE_WAVE3=1']
    s['OTHER_LDFLAGS'] = ['$(inherited)', '-lreader_desktop_metadata', '-lreader_reading_commands', '-lreader_annotation_view',
      '-lreader_navigation', '-lreader_search', '-lreader_session', '-lreader_sync', '-lexr_webdav', '-lreader_commands',
      '-lreader_reading_state_codec', '-lreader_revisions', '-lreader_revision_hash', '-lreader_catalog',
      '-lreader_catalog_sqlite', '-lexr_credentials', '-lreader_annotation_import', '-lreader_annotation_export',
      '-lreader_font_library', '-lreader_original_export', '-lreader_jump_history', '-lreader_sync_view', '-lexreader',
      '-lsqlite3', '-lc++', '-lxml2', '-framework', 'Foundation', '-framework', 'CoreFoundation', '-framework', 'Security']
    conditions = (s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] || '$(inherited)').split(' ')
    before_conditions = conditions.dup
    conditions += ['EXR_APPLE_RAW3', 'EXR_APPLE_WAVE3', 'EXR_APPLE_PAGE_THEME']
    # Opt-in only: default G16 callers keep their original compilation conditions.
    if production
      conditions -= ['EXR_APPLE_HOST_REVIEW', 'EXR_APPLE_IMPORT_REVIEW', 'EXR_APPLE_READING_REVIEW']
      production_records << { target: target.name, configuration: config.name, before: before_conditions, after: conditions.uniq }
    end
    s['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = conditions.uniq.join(' ')
  end
end
project.save
puts "product overlay applied to #{project_path} with #{products}"
puts JSON.generate(mode: "production", application_conditions: production_records) if production
