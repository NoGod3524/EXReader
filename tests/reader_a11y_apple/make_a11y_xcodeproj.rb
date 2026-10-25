#!/usr/bin/env ruby
# SPDX-License-Identifier: MIT
# G16 Actions-side project generation for the independent Apple accessibility
# audit.
#
# It mirrors tests/apple_host/make_xcodeproj.rb: the same installed-SDK linkage,
# the same app build settings and the same UI test bundle shape. Two deliberate
# differences keep this an audit of the shipped program:
#   * no EXR_APPLE_HOST_REVIEW / EXR_APPLE_IMPORT_REVIEW compilation conditions,
#     so the audited app is the plain host rather than a review build;
#   * the UI test target links only the audit directory, so the existing
#     acceptance suite stays untouched and separately owned.
# The baseline generator and the existing Apple workflows are not modified.
require 'xcodeproj'
require 'fileutils'
require 'pathname'

root = Dir.pwd
output = File.expand_path(ARGV[0] || File.join(root, 'build/a11y-apple'))
resources = File.expand_path(ARGV[1] || File.join(root, 'build/apple-resources'))
test_directory = File.expand_path(ARGV[2] || File.join(root, 'tests/reader_a11y_apple'))
project_path = File.join(output, 'EXReaderA11y.xcodeproj')
FileUtils.mkdir_p(output)
FileUtils.rm_rf(project_path)

project = Xcodeproj::Project.new(project_path)
project.root_object.attributes['LastSwiftUpdateCheck'] = '1600'
project.root_object.attributes['LastUpgradeCheck'] = '1600'

host_group = project.main_group.new_group('Host')
resource_group = project.main_group.new_group('Resources')

sources = Dir[File.join(root, 'examples/apple/*.swift')].sort +
          [File.join(root, 'bindings/swift/EXReader.swift')]
test_sources = Dir[File.join(test_directory, '*.swift')].sort
raise "no audit test sources in #{test_directory}" if test_sources.empty?
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
    settings['CLANG_ENABLE_MODULES'] = 'YES'
    settings['EXR_SDK_DIR'] = '$(SRCROOT)/sdk'
    settings['OTHER_LDFLAGS'] = ['$(inherited)', '-lexreader', '-lsqlite3']
    settings['LIBRARY_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/lib']
    settings['HEADER_SEARCH_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/include']
    settings['SWIFT_INCLUDE_PATHS'] = ['$(inherited)', '$(EXR_SDK_DIR)/include']
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
    settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.a11y.uitests'
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
  app_name = "EXReaderA11yHost-#{label}"
  test_name = "EXReaderA11yUITests-#{label}"
  app = project.new_target(:application, app_name, platform, deployment)
  app.add_file_references(source_refs)
  app.add_resources(resource_refs)
  source_sha = ENV.fetch('GITHUB_SHA')
  raise 'immutable source SHA required' unless source_sha.match?(/\A[0-9a-f]{40}\z/)
  info_plist = File.join(output, "Info-#{label}.plist")
  Xcodeproj::Plist.write_to_path({'EXRSourceSHA' => source_sha}, info_plist)
  app_settings(app, platform, deployment, info_plist)
  embed_phase(app)

  ui = make_ui_target(project, test_name, platform, deployment)
  ui.add_file_references(test_refs)
  test_settings(ui, app_name, platform)
  ui.add_dependency(app)

  scheme = Xcodeproj::XCScheme.new
  scheme.add_build_target(app)
  scheme.add_test_target(ui)
  scheme.set_launch_target(app)
  scheme.save_as(project.path, "EXReaderA11y-#{label}", true)
end

project.save
puts "wrote #{project_path} for #{test_sources.size} audit sources"
