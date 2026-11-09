"""Pinned Bandit entrypoint with no project-controlled configuration."""
import sys
sys.path.insert(0,'/opt/runtime/lib/python3.12/site-packages')
from bandit.cli.main import main
sys.argv=['bandit','-r','/work','--ini','/opt/bandit.ini','-q','-ll','--ignore-nosec']
raise SystemExit(main())
