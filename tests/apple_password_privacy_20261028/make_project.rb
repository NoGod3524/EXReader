# SPDX-License-Identifier: MIT
require 'xcodeproj'
require 'fileutils'
require 'json'
require 'digest'
require 'rbconfig'
require_relative 'project_flags'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
output, resources, proof = ARGV.first(3).map { |path| File.expand_path(path) }
platform = ARGV[3]
raise 'explicit platform' unless ['macos', 'iphone', 'ipad'].include?(platform)
FileUtils.mkdir_p(output); FileUtils.mkdir_p(proof)
def once(text, before, after)
  raise 'source anchor changed' unless text.scan(Regexp.new(Regexp.escape(before))).length == 1
  text.sub(before, after)
end
original_generator = File.join(Dir.pwd, 'tests/apple_host/make_xcodeproj.rb')
original_wrapper = File.join(Dir.pwd, 'tests/reader_team24_apple/make_project.rb')
generator = once(File.read(original_generator), "['3.40.0', '3.41.0'].include?(sdk_version)", "['3.42.0'].include?(sdk_version)")
generator = once(generator, "page_theme == 'ON' && sdk_version != '3.41.0'", "page_theme == 'ON' && sdk_version != '3.42.0'")
generated = File.join(output, 'make_xcodeproj_sdk342.rb'); File.write(generated, generator)
wrapper = once(File.read(original_wrapper), "'tests/apple_host/make_xcodeproj.rb'", generated.inspect)
wrapped = File.join(output, 'make_project_sdk342.rb'); File.write(wrapped, wrapper)
raise 'generator failed' unless system(RbConfig.ruby, wrapped, output, resources,
  File.join(Dir.pwd, 'tests/apple_password_privacy_20261028/ui'), 'wave3')
project = Xcodeproj::Project.open(File.join(output, 'EXReaderHost.xcodeproj'))
project.targets.each do |target|
  target.build_configurations.each do |config|
    settings = config.build_settings
    if target.product_type == 'com.apple.product-type.application'
      settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.password-privacy-20261028'
      settings['OTHER_SWIFT_FLAGS'] = PrivacyProjectFlags.with_raw_metadata(settings['OTHER_SWIFT_FLAGS'])
    else
      settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'org.exreader.password-privacy-20261028.tests'
      settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = platform == 'ipad' ? '$(inherited) EXR_PRIVACY_IPAD' : '$(inherited)'
    end
  end
end
project.save
files = {'original-generator.rb' => original_generator, 'derived-generator.rb' => generated,
         'original-wrapper.rb' => original_wrapper, 'derived-wrapper.rb' => wrapped}
records = files.to_h do |name, path|
  FileUtils.cp(path, File.join(proof, name))
  [name, Digest::SHA256.file(path).hexdigest]
end
File.write(File.join(proof, 'adapter.json'), JSON.pretty_generate({
  'source_sha' => ENV.fetch('GITHUB_SHA'), 'platform' => platform,
  'product_source_changed' => false, 'generator_path' => generated, 'files' => records,
  'bundle_id' => 'org.exreader.password-privacy-20261028',
  'product_sources' => (Dir['examples/apple/*.swift'].sort + ['bindings/swift/EXReader.swift']).to_h { |path| [path, Digest::SHA256.file(path).hexdigest] },
  'fixture_import_control' => true, 'credential_controls_replaced' => false,
  'profile' => ['SDK342 exact guard', 'raw selectors', 'wave3', 'page theme', 'raw metadata', 'isolated test bundle']
}) + "\n")
