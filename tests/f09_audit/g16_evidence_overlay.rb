# Only the temporary generated iOS UI test target receives the new collector.
require 'xcodeproj'
require 'pathname'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
project_path, source = ARGV
raise 'explicit project and collector required' unless project_path && source
project = Xcodeproj::Project.open(project_path)
targets = project.targets.select { |t| t.name == 'EXReaderHostUITests-iOS' }
raise 'iOS UI target not unique' unless targets.length == 1
target = targets.first
other_sources = project.targets.reject { |t| t.name == target.name }.to_h do |t|
  [t.name, t.source_build_phase.files_references.map { |ref| ref.real_path.to_s }.sort]
end
raise 'not UI test bundle' unless target.product_type == 'com.apple.product-type.bundle.ui-testing'
full_source = File.expand_path(source)
raise 'collector missing' unless File.file?(full_source)
before = target.source_build_phase.files_references.map(&:real_path).map(&:to_s)
raise 'collector already present' if before.include?(full_source)
relative = Pathname.new(full_source).relative_path_from(Pathname.new(File.dirname(File.expand_path(project_path)))).to_s
reference = project.new_file(relative)
target.add_file_references([reference])
project.save
saved = Xcodeproj::Project.open(project_path)
saved_targets = saved.targets.select { |t| t.name == 'EXReaderHostUITests-iOS' }
raise 'saved iOS UI target not unique' unless saved_targets.length == 1
after = saved_targets.first.source_build_phase.files_references.map { |ref| ref.real_path.to_s }.sort
raise 'unexpected collector source phase delta' unless after == (before + [full_source]).sort
saved_others = saved.targets.reject { |t| t.name == target.name }.to_h do |t|
  [t.name, t.source_build_phase.files_references.map { |ref| ref.real_path.to_s }.sort]
end
raise 'other target source phase changed' unless saved_others == other_sources
puts "Added one collector to #{target.name}; existing sources unchanged."
