"""Bound both pipes while running, terminate the standalone process group."""
import os
import selectors
import signal
import time
from .policy import PolicyError

def bounded_output(proc,timeout=150,limit=4*1024*1024):
 selector=selectors.DefaultSelector();output=bytearray();total=0;start=time.monotonic()
 for pipe in (proc.stdout,proc.stderr):selector.register(pipe,selectors.EVENT_READ)
 try:
  while selector.get_map():
   if time.monotonic()-start>timeout:raise PolicyError('GENERATION_TIMEOUT')
   for key,_ in selector.select(.1):
    chunk=os.read(key.fileobj.fileno(),65536)
    if not chunk:selector.unregister(key.fileobj);continue
    total+=len(chunk)
    if total>limit:raise PolicyError('GENERATION_OUTPUT_LIMIT')
    if key.fileobj is proc.stdout:output.extend(chunk)
  proc.wait(timeout=max(.01,timeout-(time.monotonic()-start)))
  return bytes(output)
 finally:
  try:os.killpg(proc.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  proc.wait();selector.close();proc.stdout.close();proc.stderr.close()
