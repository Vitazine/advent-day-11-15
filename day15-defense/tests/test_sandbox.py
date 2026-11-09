import unittest
from pathlib import Path
from runner.sandbox import Sandbox, SandboxError, build_unit_command
from runner.contracts import Snapshot,ReviewFile

class SandboxTests(unittest.TestCase):
    def test_no_remote_transport_is_not_host_fallback(self):
        s=Snapshot('a'*64,'a'*64,(ReviewFile('a.py','pass'),))
        with self.assertRaises(SandboxError):Sandbox(None).run(s)
    def test_security_properties_are_mandatory(self):
        cmd=build_unit_command(Path('/var/lib/day15-defense/jobs/abc/root'),'day15-job-abc')
        for required in ('PrivateNetwork=yes','DynamicUser=yes','NoNewPrivileges=yes','ProtectSystem=strict','MemoryMax=192M','MemorySwapMax=0','CPUQuota=50%','TasksMax=64','RuntimeMaxSec=120','KillMode=control-group'):
            self.assertIn(required,cmd)
        self.assertIn('/usr/bin/python3',cmd)
        self.assertNotIn('sh',cmd)
    def test_command_rejects_root_and_unit_injection(self):
        for root,unit in [('/etc','day15-job-abc'),('/var/lib/day15-defense/jobs/../root','x'),('/var/lib/day15-defense/jobs/abc/root','bad/name')]:
            with self.subTest(root=root),self.assertRaises(SandboxError):build_unit_command(Path(root),unit)
