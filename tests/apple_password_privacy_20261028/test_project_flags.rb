# SPDX-License-Identifier: MIT
require 'xcodeproj'
require 'tmpdir'
require_relative 'project_flags'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'

base = ['$(inherited)', '-Xcc', '-DEXR_READER_SELECTOR_BYTES_CANDIDATE=1', '-Xcc', '-DEXR_APPLE_WAVE3=1']
expected = base + ['-Xcc', '-DEXR_READER_METADATA_RAW3=1']
raise 'Array flags changed' unless PrivacyProjectFlags.with_raw_metadata(base) == expected
raise 'caller Array mutated' unless base.length == 5
raise 'String flags changed' unless PrivacyProjectFlags.with_raw_metadata(base.join(' ')) == expected
quoted = '$(inherited) -I "a path/with spaces"'
raise 'quoted path split' unless PrivacyProjectFlags.with_raw_metadata(quoted) ==
  ['$(inherited)', '-I', 'a path/with spaces', '-Xcc', '-DEXR_READER_METADATA_RAW3=1']
[nil, 1, [], ['ok', 1], [''], ''].each do |invalid|
  rejected = false
  begin
    PrivacyProjectFlags.with_raw_metadata(invalid)
  rescue RuntimeError
    rejected = true
  end
  raise 'invalid flags accepted' unless rejected
end
rejected = false
begin
  PrivacyProjectFlags.with_raw_metadata('"unterminated')
rescue ArgumentError
  rejected = true
end
raise 'malformed quoting accepted' unless rejected

Dir.mktmpdir('privacy-project-flags-') do |folder|
  path = File.join(folder, 'Flags.xcodeproj')
  project = Xcodeproj::Project.new(path)
  target = project.new_target(:application, 'Flags', :osx, '13.0')
  target.build_configurations.each { |config| config.build_settings['OTHER_SWIFT_FLAGS'] = base }
  project.save
  reopened = Xcodeproj::Project.open(path)
  reopened.targets.first.build_configurations.each do |config|
    original = config.build_settings['OTHER_SWIFT_FLAGS']
    config.build_settings['OTHER_SWIFT_FLAGS'] = PrivacyProjectFlags.with_raw_metadata(original)
  end
  reopened.save
  Xcodeproj::Project.open(path).targets.first.build_configurations.each do |config|
    value = config.build_settings['OTHER_SWIFT_FLAGS']
    actual = value.is_a?(String) ? Shellwords.split(value) : value
    raise 'actual xcodeproj roundtrip lost flags' unless actual == expected
  end
end
puts 'PASS: String/Array/quoted flags, invalid inputs, actual xcodeproj save/reopen preserve all flags'
