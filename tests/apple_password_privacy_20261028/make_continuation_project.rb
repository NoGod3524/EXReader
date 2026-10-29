# SPDX-License-Identifier: MIT
require 'xcodeproj'
require 'rbconfig'
require 'digest'
require 'json'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
output, resources, proof, platform = ARGV
strict = File.join(Dir.pwd, 'tests/apple_password_privacy_20261028/make_project.rb')
raise 'strict generated project failed' unless system(RbConfig.ruby, strict, output, resources, proof, platform)
project_path = File.join(output, 'EXReaderHost.xcodeproj')
project = Xcodeproj::Project.open(project_path)
files = project.files.select { |file| File.basename(file.path.to_s) == 'PasswordPrivacyUITests.swift' }
raise 'strict test reference differs' unless files.length == 1
probe = File.join(Dir.pwd, 'tests/apple_password_privacy_20261028/continuation_ui/PasswordPrivacyContinuationUITests.swift')
before = File.join(project_path, 'project.pbxproj')
File.write(File.join(proof, 'strict-project.pbxproj'), File.binread(before))
files.first.path = probe
files.first.source_tree = '<absolute>'
project.save
File.write(File.join(proof, 'continuation-project.pbxproj'), File.binread(before))
File.write(File.join(proof, 'continuation-adapter.json'), JSON.pretty_generate({
  'diagnostic_only' => true, 'source_sha' => ENV.fetch('GITHUB_SHA'), 'platform' => platform,
  'strict_test_replaced_only_in_generated_probe_target' => true,
  'strict_test_sha256' => Digest::SHA256.file(File.join(Dir.pwd, 'tests/apple_password_privacy_20261028/ui/PasswordPrivacyUITests.swift')).hexdigest,
  'continuation_test_sha256' => Digest::SHA256.file(probe).hexdigest,
  'strict_project_sha256' => Digest::SHA256.file(File.join(proof, 'strict-project.pbxproj')).hexdigest,
  'continuation_project_sha256' => Digest::SHA256.file(File.join(proof, 'continuation-project.pbxproj')).hexdigest
}) + "\n")
