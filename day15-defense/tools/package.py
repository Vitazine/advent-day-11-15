"""Allowlisted source package. Runtime state, credentials and logs never included."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

class PackageError(RuntimeError):pass
ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES={'api','runner','server','sandbox','tools','tests','redteam','integration'}
TOP={'PARTNER_START.md','requirements-api.txt','README.md','requirements.txt','requirements-worker.txt'}
EXTENSIONS={'.py','.json','.ini','.md'}
SECRET=re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:sk-|ghp_)[A-Za-z0-9_-]{24,}')

def package(root,output):
 entries=[]
 for path in sorted(root.rglob('*')):
  rel=path.relative_to(root)
  if path.is_symlink():continue
  if not path.is_file() or '__pycache__' in rel.parts:continue
  if not (str(rel) in TOP or (rel.parts[0] in DIRECTORIES and path.suffix in EXTENSIONS)):continue
  data=path.read_bytes()
  if SECRET.search(data):raise PackageError('SECRET_PATTERN_IN_PACKAGE')
  entries.append((rel.as_posix(),data))
 # Include the exact gateway guard used by the synthetic regression corpus.
 reference=root.parent/'day14-v2/gateway'
 if reference.is_dir():
  for name in ('__init__.py','guards.py','contracts.py'):
   data=(reference/name).read_bytes()
   if SECRET.search(data):raise PackageError('SECRET_PATTERN_IN_PACKAGE')
   entries.append(('gateway/'+name,data))
 manifest={name:hashlib.sha256(data).hexdigest() for name,data in entries}
 output.parent.mkdir(parents=True,exist_ok=True)
 with tarfile.open(output,'w:gz') as archive:
  for name,data in entries+[('MANIFEST.json',json.dumps(manifest,indent=2).encode())]:
   info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
   archive.addfile(info,io.BytesIO(data))
 return manifest

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist/day15-defense.tgz');args=parser.parse_args()
 manifest=package(ROOT,args.output);print(json.dumps({'files':len(manifest),'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
