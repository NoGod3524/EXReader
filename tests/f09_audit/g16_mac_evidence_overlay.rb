# Only temporary macOS UI test target gets one collector; old refs stay exact.
require 'xcodeproj'
require 'pathname'
require 'json'
raise 'Actions only' unless ENV['GITHUB_ACTIONS'] == 'true'
project_path, source = ARGV
raise 'explicit project and collector required' unless project_path && source
def phase_signature(target)
  target.source_build_phase.files.map do |file|
    ref = file.file_ref
    raise 'source build file missing reference' unless ref
    [file.uuid, ref.uuid, ref.path, ref.source_tree, JSON.generate(file.settings || {})]
  end.sort_by { |row| row[0] }
end
project = Xcodeproj::Project.open(project_path)
targets = project.targets.select { |t| t.name == 'EXReaderHostUITests-macOS' }
raise 'macOS UI target not unique' unless targets.length == 1
target = targets.first
raise 'not UI test bundle' unless target.product_type == 'com.apple.product-type.bundle.ui-testing'
before = phase_signature(target)
others = project.targets.reject { |t| t.name == target.name }.to_h { |t| [t.name, phase_signature(t)] }
full_source = File.expand_path(source)
raise 'collector missing' unless File.file?(full_source)
relative = Pathname.new(full_source).relative_path_from(Pathname.new(File.dirname(File.expand_path(project_path)))).to_s
raise 'collector path already referenced' if before.any? { |row| row[2] == relative }
reference = project.new_file(relative)
raise 'new reference path mismatch' unless reference.path == relative && reference.source_tree == '<group>'
target.add_file_references([reference])
added = phase_signature(target).reject { |row| before.include?(row) }
raise 'expected exactly one new collector build reference' unless added.length == 1 && added[0][1] == reference.uuid
expected = (before + added).sort_by { |row| row[0] }
project.save
saved = Xcodeproj::Project.open(project_path)
saved_targets = saved.targets.select { |t| t.name == target.name }
raise 'saved macOS UI target not unique' unless saved_targets.length == 1
raise 'unexpected source phase delta' unless phase_signature(saved_targets.first) == expected
saved_others = saved.targets.reject { |t| t.name == target.name }.to_h { |t| [t.name, phase_signature(t)] }
raise 'other source phases changed' unless saved_others == others
saved_ref = saved.objects_by_uuid[reference.uuid]
raise 'saved new source reference mismatch' unless saved_ref &&
  saved_ref.path == relative && saved_ref.source_tree == '<group>'
puts "Added one collector source reference; all prior source phase signatures unchanged."
