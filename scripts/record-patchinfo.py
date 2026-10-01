"""Refresh source hashes after upstream formatting."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / 'ish-compat/PATCHINFO.json'
data = json.loads(path.read_text())
for name in data['patched_source_sha256']:
    data['patched_source_sha256'][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
path.write_text(json.dumps(data, indent=2) + '\n')
