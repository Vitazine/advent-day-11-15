import hashlib
import tempfile
import unittest
from pathlib import Path
from tools.doctor import inspect_client, inspect_runtime, readiness

class DoctorTests(unittest.TestCase):
    def test_missing_client_fails_closed(self):
        self.assertEqual(inspect_client(Path('/nonexistent/day15'), '2.2.6', '0'*64)['status'], 'missing')

    def test_digest_mismatch_does_not_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'client'
            marker=Path(tmp)/'executed'
            binary.write_text(f'#!/bin/sh\ntouch "{marker}"\n');binary.chmod(0o700)
            self.assertEqual(inspect_client(binary,'2.2.6','0'*64)['status'],'digest_mismatch')
            self.assertFalse(marker.exists())

    def test_matching_digest_is_only_identity_not_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'client';binary.write_bytes(b'synthetic binary')
            result=inspect_client(binary,'2.2.6',hashlib.sha256(binary.read_bytes()).hexdigest())
            self.assertEqual(result['status'],'verified_identity')
            self.assertFalse(readiness(result,{'status':'available'})['ready'])

    def test_missing_runtime_has_no_host_fallback(self):
        result=inspect_runtime(None)
        self.assertEqual(result['status'],'missing')
        self.assertFalse(readiness({'status':'verified_identity'},result)['ready'])

    def test_executable_without_linux_daemon_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'docker';binary.write_text('#!/bin/sh\nexit 1\n');binary.chmod(0o700)
            self.assertEqual(inspect_runtime(binary)['status'],'unavailable')

    def test_darwin_daemon_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'docker';binary.write_text('#!/bin/sh\necho darwin\n');binary.chmod(0o700)
            self.assertEqual(inspect_runtime(binary)['status'],'not_linux')
