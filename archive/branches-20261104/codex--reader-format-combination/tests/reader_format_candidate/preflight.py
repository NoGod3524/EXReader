import json
from common import guard, combined_tree, PATCHES, WORK, write
from test_protocol import main

if __name__ == '__main__':
    result = guard()
    main()
    trees = combined_tree()
    assert trees == combined_tree(list(reversed(PATCHES)))
    write(WORK / 'guard/trees.json', trees)
    print(json.dumps({'guard_ok': result['ok'], 'source_sha': result['source_sha'],
                      'manifest_v2_sha256': result['manifest_v2_sha256']}), flush=True)
