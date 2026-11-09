import tempfile
import unittest
import hashlib
import json
from pathlib import Path
from tools.configure import configure

class ConfigureTests(unittest.TestCase):
    def test_files_private_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'credentials';configure(target,'synthetic-upstream-key')
            token=(target/'proxy-token').read_text().strip();hashes=json.loads((target/'tokens.json').read_text())
            self.assertEqual(hashes[token.split('.')[0]],hashlib.sha256(token.encode()).hexdigest())
            for p in target.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)
            with self.assertRaises(FileExistsError):configure(target,'replacement')
