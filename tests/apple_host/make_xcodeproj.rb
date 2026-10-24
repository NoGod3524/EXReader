#!/usr/bin/env ruby
# SPDX-License-Identifier: MIT
# Generate the Xcode project used only for WP13 UI acceptance. The shipped host
# is still built by tools/build_apple_host.py against an installed SDK.
require 'xcodeproj'
require 'fileutils'
require 'pathname'

root = Dir.pwd
output = File.expand_path(ARGV[0] || File.join(root, 'build/apple-host'))
resources = File.expand_path(ARGV[1] || File.join(root, 'build/apple-resources'))
project_path = File.join(output, 'EXReaderHost.xcodeproj')
FileUtils.mkdir_p(output)
FileUtils.rm_rf(project_path)

project = Xcodeproj::Project.new(project_path)
project.root_object.attributes['LastSwiftUpdateCheck'] = '1600'
project.root_object.attributes['LastUpgradeCheck'] = '1600'

host_group = project.main_group.new_group('Host')
resource_group = project.main_group.new_group('Resources')

sources = Dir[File.join(root, 'examples/apple/*.swift')].sort +
          [File.join(root, 'bindings/swift/EXReader.swift')]
test_directory = ARGV[2] ? File.expand_path(ARGV[2]) : File.join(root, 'tests/apple_host')
test_sources = Dir[File.join(test_directory, '*.swift')].sort
resource_files = Dir[File.join(resources, '*')].sort

base = Pathname.new(output)
def relative(base, file)
  Pathname.new(File.expand_path(file)).relative_path_from(base).to_s
end
source_refs = sources.map { |file| project.new_file(relative(base, file)) }
host_group.children.concat(source_refs)
test_refs = test_sources.map { |file| project.new_file(relative(base, file)) }
host_group.children.concat(test_refs)
resource_refs = resource_files.map { |file| project.new_file(relative(base, file)) }
resource_group.children.concat(resource_refs)

def app_settings(target, platform, deployment, info_plist)
  target.build_configurations.each do |config|
    settings = config.build_settings
    settings['SWIFT_VERSION'] = '5.0'
    settings['PRODUCT_NAME'] = 'EXReaderHost'
    settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.host'
    settings['GENERATE_INFOPLIST_FILE'] = 'YES'
    settings['INFOPLIST_FILE'] = info_plist
    settings['INFOPLIST_KEY_CFBundleDisplayName'] = 'EXReader'
    settings['CURRENT_PROJECT_VERSION'] = '1'
    settings['MARKETING_VERSION'] = '1.0'
    settings['CODE_SIGN_STYLE'] = 'Manual'
    settings['CODE_SIGN_IDENTITY'] = '-'
    settings['ENABLE_HARDENED_RUNTIME'] = 'NO'
    settings['ENABLE_APP_SANDBOX'] = 'NO'
    settings['ENABLE_USER_SCRIPT_SANDBOXING'] = 'NO'
    # Keep the actual host in its executable, like the shipped standalone
    # package; Xcode's preview stub otherwise owns no product SQLite symbols.
    settings['ENABLE_DEBUG_DYLIB'] = 'NO'
    settings['CLANG_ENABLE_MODULES'] = 'YES'
    settings['EXR_SDK_DIR'] = '$(SRCROOT)/sdk'
    settings['OTHER_LDFLAGS'] = ['$(inherited)', '-lreader_navigation', '-lreader_search', '-lreader_session', '-lreader_sync',
      '-lexr_webdav', '-lreader_commands', '-lreader_reading_state_codec', '-lreader_revisions',
      '-lreader_revision_hash', '-lreader_catalog', '-lreader_catalog_sqlite', '-lexr_credentials', '-lexreader',
      '-lc++', '-lxml2', '-framework', 'Foundation', '-framework', 'CoreFoundation', '-framework', 'Security']
    settings['LD_GENERATE_MAP_FILE'] = 'YES'
    settings['LD_MAP_FILE_PATH'] = '$(TARGET_BUILD_DIR)/$(PRODUCT_NAME).link.map'
    settings['LIBRARY_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/lib']
    settings['HEADER_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/include', '$(EXR_SDK_DIR)/include/exreader-product']
    settings['SWIFT_INCLUDE_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/include',
      '$(EXR_SDK_DIR)/include/exreader-product', File.join(Dir.pwd, 'examples/apple/product')]
    settings['LD_RUNPATH_SEARCH_PATHS'] = ['$(inherited)', '@executable_path/Frameworks',
                                            '@executable_path/../Frameworks']
    if platform == :ios
      settings['SDKROOT'] = 'iphoneos'
      settings['SUPPORTED_PLATFORMS'] = 'iphonesimulator iphoneos'
      settings['IPHONEOS_DEPLOYMENT_TARGET'] = deployment
      settings['TARGETED_DEVICE_FAMILY'] = '1,2'
      settings['SUPPORTS_MACCATALYST'] = 'NO'
      settings['CODE_SIGNING_ALLOWED'] = 'NO'
      settings['CODE_SIGNING_REQUIRED'] = 'NO'
      settings['INFOPLIST_KEY_UILaunchScreen_Generation'] = 'YES'
      settings['INFOPLIST_KEY_UIFileSharingEnabled'] = 'YES'
      settings['INFOPLIST_KEY_LSSupportsOpeningDocumentsInPlace'] = 'YES'
      settings['INFOPLIST_KEY_UISupportedInterfaceOrientations'] =
        'UIInterfaceOrientationPortrait UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight'
      settings['INFOPLIST_KEY_UISupportedInterfaceOrientations_iPad'] =
        'UIInterfaceOrientationPortrait UIInterfaceOrientationPortraitUpsideDown ' \
        'UIInterfaceOrientationLandscapeLeft UIInterfaceOrientationLandscapeRight'
    else
      settings['SDKROOT'] = 'macosx'
      settings['SUPPORTED_PLATFORMS'] = 'macosx'
      settings['MACOSX_DEPLOYMENT_TARGET'] = deployment
      settings['INFOPLIST_KEY_LSApplicationCategoryType'] = 'public.app-category.books'
      settings['CODE_SIGNING_ALLOWED'] = 'YES'
    end
  end
end

def test_settings(target, app_name, platform)
  target.build_configurations.each do |config|
    settings = config.build_settings
    settings['SWIFT_VERSION'] = '5.0'
    settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.host.uitests'
    settings['TEST_TARGET_NAME'] = app_name
    settings['GENERATE_INFOPLIST_FILE'] = 'YES'
    settings['CODE_SIGN_STYLE'] = 'Manual'
    settings['CODE_SIGN_IDENTITY'] = '-'
    settings['CODE_SIGNING_REQUIRED'] = platform == :ios ? 'NO' : 'YES'
    settings['CODE_SIGNING_ALLOWED'] = platform == :ios ? 'NO' : 'YES'
    settings['LD_RUNPATH_SEARCH_PATHS'] = ['$(inherited)', '@executable_path/Frameworks',
                                            '@loader_path/Frameworks']
    settings['ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES'] = 'YES'
  end
end

def embed_phase(target)
  phase = target.new_shell_script_build_phase('Embed EXReader runtime')
  phase.shell_script = <<~SCRIPT
    set -e
    DEST="${TARGET_BUILD_DIR}/${FRAMEWORKS_FOLDER_PATH}"
    mkdir -p "$DEST"
    cp -f "$EXR_SDK_DIR"/lib/libexreader*.dylib "$DEST"/
    if [ "$PLATFORM_NAME" = "macosx" ]; then
      for lib in "$DEST"/libexreader*.dylib; do
        codesign --force --sign - "$lib"
      done
    fi
    python3 "#{File.join(Dir.pwd, 'tools/check_apple_product.py')}" \\
      --binary "${TARGET_BUILD_DIR}/${EXECUTABLE_PATH}" --map "${LD_MAP_FILE_PATH}" \\
      --output "${TARGET_BUILD_DIR}/product-link.json"
  SCRIPT
end

def make_ui_target(project, name, platform, deployment)
  begin
    project.new_target(:ui_test_bundle, name, platform, deployment)
  rescue StandardError
    target = project.new_target(:unit_test_bundle, name, platform, deployment)
    target.product_type = 'com.apple.product-type.bundle.ui-testing'
    target
  end
end

[[:osx, 'macOS', '12.0'], [:ios, 'iOS', '15.0']].each do |platform, label, deployment|
  app_name = "EXReaderHost-#{label}"
  test_name = "EXReaderHostUITests-#{label}"
  app = project.new_target(:application, app_name, platform, deployment)
  app.add_file_references(source_refs)
  app.add_resources(resource_refs)
  source_sha = ENV.fetch('GITHUB_SHA')
  raise 'immutable source SHA required' unless source_sha.match?(/\A[0-9a-f]{40}\z/)
  info_plist = File.join(output, "Info-#{label}.plist")
  # Xcode's generated standard keys augment this explicit source plist. Custom
  # INFOPLIST_KEY settings alone did not survive the cloud product generation.
  Xcodeproj::Plist.write_to_path({'EXRSourceSHA' => source_sha}, info_plist)
  app_settings(app, platform, deployment, info_plist)
  app.build_configurations.each do |config|
    conditions = ['$(inherited)']
    # Original UI acceptance retains its diagnostic observations. Accessibility
    # regression uses the production semantic tree without debug identities.
    conditions << 'EXR_APPLE_HOST_REVIEW' unless test_directory.include?('/accessibility/')
    if ARGV[2]
      review = if test_directory.include?('/shelf/')
        'EXR_APPLE_SHELF_REVIEW'
      elsif test_directory.include?('/account/')
        'EXR_APPLE_ACCOUNT_REVIEW'
      elsif test_directory.include?('/accessibility/')
        nil
      elsif test_directory.include?('/search/') || test_directory.include?('/navigation/')
        nil
      else
        'EXR_APPLE_IMPORT_REVIEW'
      end
      conditions << review if review
    end
    config.build_settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = conditions.join(' ')
  end
  embed_phase(app)

  ui = make_ui_target(project, test_name, platform, deployment)
  ui.add_file_references(test_refs)
  test_settings(ui, app_name, platform)
  ui.add_dependency(app)

  scheme = Xcodeproj::XCScheme.new
  scheme.add_build_target(app)
  scheme.add_test_target(ui)
  scheme.set_launch_target(app)
  scheme.save_as(project.path, app_name, true)
end

project.save
puts "wrote #{project_path}"
