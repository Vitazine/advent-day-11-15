"""Bounded, non-executing source import with descriptor-relative traversal."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
from .contracts import ReviewFile, Snapshot

MAX_BYTES=192*1024
MAX_FILES=20
FORBIDDEN={'.git','.opencode','opencode.json','opencode.jsonc','conftest.py','sitecustomize.py','usercustomize.py','.env'}

class SnapshotError(ValueError):
    pass

def canonical(files):
    return json.dumps([[f.path,f.content] for f in files],ensure_ascii=False,separators=(',',':')).encode('utf-8')

def validate(items):
    if not isinstance(items,(list,tuple)) or not 1<=len(items)<=MAX_FILES:
        raise SnapshotError('FILE_LIMIT')
    result=[];names=set();size=0
    for pair in items:
        if not isinstance(pair,(tuple,list)) or len(pair)!=2:raise SnapshotError('INVALID_FILE')
        name,content=pair
        if not isinstance(name,str) or not isinstance(content,str):raise SnapshotError('INVALID_FILE')
        parts=name.split('/')
        if len(name)>240 or len(parts)>16 or any(p in ('','.','..') or p.casefold() in FORBIDDEN for p in parts):
            raise SnapshotError('PATH_DENIED')
        if '\\' in name or ':' in name or any(ord(c)<32 for c in name) or unicodedata.normalize('NFC',name)!=name:
            raise SnapshotError('PATH_DENIED')
        if name.casefold() in names:raise SnapshotError('PATH_COLLISION')
        names.add(name.casefold())
        try:size+=len(content.encode('utf-8'))
        except UnicodeError:raise SnapshotError('INVALID_UTF8') from None
        if size>MAX_BYTES:raise SnapshotError('BYTE_LIMIT')
        result.append(ReviewFile(name,content))
    return tuple(sorted(result,key=lambda f:f.path))

def open_directory(path):
    path=Path(os.path.abspath(path))
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=next_fd
        return fd
    except BaseException:
        os.close(fd);raise

class SnapshotStore:
    def __init__(self,root):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=open_directory(self.root);os.close(fd)

    def create(self,source):
        items=[];size=0;entries=0
        def walk(fd,prefix='',depth=0):
            nonlocal size,entries
            if depth>16:raise SnapshotError('DEPTH_LIMIT')
            with os.scandir(fd) as scan:
                for item in scan:
                    entries+=1
                    if entries>128:raise SnapshotError('ENTRY_LIMIT')
                    name=prefix+item.name
                    if item.name.casefold() in FORBIDDEN:raise SnapshotError('PATH_DENIED')
                    info=os.stat(item.name,dir_fd=fd,follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        child=os.open(item.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                        try:walk(child,name+'/',depth+1)
                        finally:os.close(child)
                    elif stat.S_ISREG(info.st_mode):
                        child=os.open(item.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
                        try:
                            before=os.fstat(child)
                            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise SnapshotError('FILE_TYPE')
                            with os.fdopen(child,'rb',closefd=False) as stream:data=stream.read(MAX_BYTES-size+1)
                            after=os.fstat(child)
                            if (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
                                raise SnapshotError('SOURCE_CHANGED')
                        finally:os.close(child)
                        size+=len(data)
                        if size>MAX_BYTES:raise SnapshotError('BYTE_LIMIT')
                        items.append((name,data.decode('utf-8')))
                        if len(items)>MAX_FILES:raise SnapshotError('FILE_LIMIT')
                    else:raise SnapshotError('FILE_TYPE')
        try:
            fd=open_directory(source)
            try:walk(fd)
            finally:os.close(fd)
            return self.from_files(items)
        except (OSError,UnicodeError):raise SnapshotError('IMPORT_FAILED') from None

    def from_files(self,items):
        files=validate(items);data=canonical(files);digest=hashlib.sha256(data).hexdigest()
        # JSON escaping can expand payload beyond its source-byte bound.
        if len(data)>240*1024:raise SnapshotError('PAYLOAD_LIMIT')
        path=self.root/f'{digest}.json'
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError:return self.open(digest)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno());os.fchmod(stream.fileno(),0o400)
        return Snapshot(digest,digest,files)

    def open(self,snapshot_id):
        if not isinstance(snapshot_id,str) or not re.fullmatch('[0-9a-f]{64}',snapshot_id):raise SnapshotError('INVALID_ID')
        try:
            fd=os.open(self.root/f'{snapshot_id}.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise SnapshotError('FILE_TYPE')
                data=stream.read(240*1024+1)
            if len(data)>240*1024 or hashlib.sha256(data).hexdigest()!=snapshot_id:raise SnapshotError('HASH_MISMATCH')
            files=validate(json.loads(data))
            if canonical(files)!=data:raise SnapshotError('NONCANONICAL')
            return Snapshot(snapshot_id,snapshot_id,files)
        except (OSError,UnicodeError,json.JSONDecodeError):raise SnapshotError('INVALID_SNAPSHOT') from None
