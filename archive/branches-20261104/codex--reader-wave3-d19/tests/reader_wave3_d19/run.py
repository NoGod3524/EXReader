"""Execute original 24-cycle/30-second D14 runner with the new native driver."""
import sys
from reuse import source
# The original loader resolves gtk.py next to this explicit adapter __file__.
# All original action, resource, dwell, cleanup and validation bodies are intact.
sys.argv = [__file__, 'gtk']
exec(compile(source('run.py'), 'immutable-D14/run.py', 'exec'), globals())
