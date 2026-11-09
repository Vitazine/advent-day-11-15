import tarfile
import tempfile
import unittest
from pathlib import Path
from tools.package import package,PackageError
class PackageTests(unittest.TestCase):
 def test_allowlist_excludes_private_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runner').mkdir();(root/'runner/a.py').write_text('pass')
   (root/'.local').mkdir();(root/'.local/token').write_text('private')
   (root/'runner/password.env').write_text('private')
   out=root/'test.tgz';package(root,out)
   with tarfile.open(out) as archive:
    self.assertEqual(sorted(archive.getnames()),['MANIFEST.json','runner/a.py'])
 def test_secret_in_source_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'runner').mkdir();(root/'runner/a.py').write_text('KEY="sk-'+('X'*36)+'"')
   with self.assertRaises(PackageError):package(root,root/'test.tgz')
