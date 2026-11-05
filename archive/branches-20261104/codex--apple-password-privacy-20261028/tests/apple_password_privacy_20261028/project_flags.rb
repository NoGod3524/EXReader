# SPDX-License-Identifier: MIT
require 'shellwords'

module PrivacyProjectFlags
  def self.with_raw_metadata(value)
    flags = case value
            when String then Shellwords.split(value)
            when Array then value.dup
            else raise 'unexpected OTHER_SWIFT_FLAGS type'
            end
    raise 'invalid OTHER_SWIFT_FLAGS tokens' unless !flags.empty? && flags.all? { |flag| flag.is_a?(String) && !flag.empty? }
    flags + ['-Xcc', '-DEXR_READER_METADATA_RAW3=1']
  end
end
