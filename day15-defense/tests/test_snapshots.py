import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from runner.snapshot import SnapshotStore, SnapshotError

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
        self.source=self.root/'source';self.source.mkdir();self.store=SnapshotStore(self.root/'store')
    def tearDown(self):self.tmp.cleanup()
    def put(self,name,data):
        p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    def test_hash_matches_gateway_canonical_format(self):
        self.put('b.py',b'b\r\n');self.put('a.py',b'a\n')
        snap=self.store.create(self.source)
        expected=hashlib.sha256(json.dumps([['a.py','a\n'],['b.py','b\r\n']],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(snap.artifact_hash,expected)
        self.assertEqual(self.store.open(snap.id),snap)
    def test_source_replacement_does_not_change_snapshot(self):
        self.put('app.py',b'original');snap=self.store.create(self.source)
        self.put('app.py',b'changed')
        self.assertEqual(self.store.open(snap.id).files[0].content,'original')
        self.assertNotEqual(self.store.create(self.source).artifact_hash,snap.artifact_hash)
    def test_rejects_symlink(self):
        (self.source/'bad.py').symlink_to('/etc/passwd')
        with self.assertRaises(SnapshotError):self.store.create(self.source)
    def test_rejects_fifo_without_hanging(self):
        os.mkfifo(self.source/'pipe')
        with self.assertRaises(SnapshotError):self.store.create(self.source)
    def test_rejects_limits_without_truncating(self):
        self.put('big.py',b'a'*(192*1024+1))
        with self.assertRaises(SnapshotError):self.store.create(self.source)
        (self.source/'big.py').unlink()
        for i in range(21):self.put(f'{i}.py',b'x')
        with self.assertRaises(SnapshotError):self.store.create(self.source)
    def test_rejects_invalid_utf8_and_case_collision(self):
        self.put('a.py',b'\xff')
        with self.assertRaises(SnapshotError):self.store.create(self.source)
        self.put('a.py',b'good');self.put('A.py',b'other')
        # macOS may be case-insensitive: run collision check on explicit import too.
        with self.assertRaises(SnapshotError):self.store.from_files([('a.py','a'),('A.py','b')])
    def test_config_rejected_and_tests_included(self):
        self.put('tests/test_app.py',b'assert True')
        snap=self.store.create(self.source)
        self.assertEqual(snap.files[0].path,'tests/test_app.py')
        self.put('opencode.json',b'{}')
        with self.assertRaises(SnapshotError):self.store.create(self.source)
    def test_tampered_store_fails_closed(self):
        self.put('app.py',b'original');snap=self.store.create(self.source)
        record=self.root/'store'/f'{snap.id}.json';record.chmod(0o600)
        record.write_text('[]')
        with self.assertRaises(SnapshotError):self.store.open(snap.id)
    def test_rejects_arbitrary_ids_paths_and_empty(self):
        with self.assertRaises(SnapshotError):self.store.open('../elsewhere')
        for files in ([],[('../x','x')],[('/x','x')],[('a\\b','x')],[('.opencode/plugin.ts','x')]):
            with self.subTest(files=files),self.assertRaises(SnapshotError):self.store.from_files(files)
