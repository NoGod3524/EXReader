import json
from common import guard
from test_protocol import main

if __name__ == '__main__':
    result = guard()
    main()
    print(json.dumps({'guard_ok': result['ok'], 'source_sha': result['source_sha'],
                      'manifest_v2_sha256': result['manifest_v2_sha256']}), flush=True)
