import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .contracts import JobRequest
from .snapshot import SnapshotStore
from .store import JobStore
from .loop import Runner
from .sandbox import Sandbox
from .accept import Acceptor

ROOT=Path(__file__).resolve().parents[1]

def main():
 parser=argparse.ArgumentParser(description='Day15 trusted runner')
 parser.add_argument('--state-dir',type=Path,default=ROOT/'.local/state')
 sub=parser.add_subparsers(dest='command',required=True)
 sub.add_parser('doctor')
 run=sub.add_parser('run');run.add_argument('--source',type=Path,required=True);run.add_argument('--task',default='')
 run.add_argument('--token-file',type=Path,default=ROOT.parent/'day14-v2/.local/credentials/proxy-token')
 for command in ('status','accept'):
  p=sub.add_parser(command);p.add_argument('job_id')
 args=parser.parse_args()
 if args.command=='doctor':
  from tools.doctor import main as doctor_main
  # Doctor owns no runner command line flags.
  import sys
  sys.argv=[sys.argv[0]]
  return doctor_main()
 if args.command=='run':
  ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=3','-o','IdentitiesOnly=yes','-i',str(Path.home()/'.ssh/day15_executor'),'deploy@executor.example.com']
  result=Runner(args.state_dir,Sandbox(ssh),args.token_file.read_text().strip()).run(JobRequest(args.source,args.task))
 else:
  jobs=JobStore(args.state_dir/'jobs.db')
  if args.command=='status':result=jobs.status(args.job_id)
  else:result=asdict(Acceptor(jobs,SnapshotStore(args.state_dir/'snapshots'),args.state_dir/'accepted').accept(args.job_id))
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if args.command!='run' or result['state']=='accepted_candidate' else 1

if __name__=='__main__':
 try:raise SystemExit(main())
 except (OSError,ValueError,RuntimeError):
  print(json.dumps({'error':'OPERATION_FAILED'}));raise SystemExit(1)
