"""One-worker durable reservations and metadata-only audit."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from .contracts import EventMeta
from .errors import GatewayError

class Ledger:
    def __init__(self,path,clock=time.time,audit_cap=20*1024*1024):
        self.path=Path(path);self.clock=clock;self.audit_cap=audit_cap
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.transaction() as db:
            db.executescript('''
            PRAGMA journal_mode=DELETE;
            CREATE TABLE IF NOT EXISTS attempts(key_id TEXT,ts REAL);
            CREATE INDEX IF NOT EXISTS attempt_key ON attempts(key_id,ts);
            CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,key_id TEXT,ts REAL,settled REAL,state TEXT,reserve INTEGER,cost INTEGER,usage TEXT,elapsed_ms INTEGER);
            CREATE INDEX IF NOT EXISTS call_key ON calls(key_id,settled);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ts REAL,event TEXT);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
            ''')
        self.path.chmod(0o600)
    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=2,isolation_level=None)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA secure_delete=ON');db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()
    def _audit(self,db,event,reserve_extra=0):
        data=event.model_dump_json(exclude_none=True)
        used=db.execute('SELECT coalesce(sum(length(CAST(event AS BLOB))),0) FROM audit').fetchone()[0]
        # Reserve room for completion so accepted requests can settle at capacity.
        active=db.execute("SELECT count(*) FROM calls WHERE state='reserved'").fetchone()[0]
        if used+len(data.encode())+4096*max(0,active+reserve_extra)>self.audit_cap:raise GatewayError('AUDIT_FULL',503)
        db.execute('INSERT INTO audit(ts,event) VALUES (?,?)',(self.clock(),data))
    def attempt(self,key_id):
        with self.transaction() as db:
            db.execute('DELETE FROM attempts WHERE ts<=?',(self.clock()-60,))
            if db.execute('SELECT count(*) FROM attempts WHERE key_id=?',(key_id,)).fetchone()[0]>=10:raise GatewayError('RATE_LIMIT',429)
            db.execute('INSERT INTO attempts VALUES (?,?)',(key_id,self.clock()))
    def _window(self,db,key_id,seconds,cap):
        sql="SELECT * FROM calls WHERE (state='reserved' OR settled>?)";params=[self.clock()-seconds]
        if key_id is not None:sql+=' AND key_id=?';params.append(key_id)
        rows=db.execute(sql,params).fetchall()
        active=[r for r in rows if r['state']=='reserved']
        reserve=sum(r['reserve'] for r in active)
        spent=sum(r['cost'] for r in rows if r['state']!='reserved')
        return dict(budget_nano=cap,reserved_nano=reserve,spent_nano=spent,
                    unknown_nano=sum(r['cost'] for r in rows if r['state']=='unknown'),
                    remaining_nano=max(0,cap-reserve-spent),active=len(active))
    def reserve(self,key_id,amount_nano,meta):
        if type(amount_nano)!=int or amount_nano<=0:raise ValueError('reserve')
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():raise GatewayError('SAFETY_HALT',503)
            for k,seconds,cap,concurrency in ((key_id,1800,100_000_000,1),(None,86400,1_000_000_000,2)):
                w=self._window(db,k,seconds,cap)
                if amount_nano>w['remaining_nano']:raise GatewayError('BUDGET_LIMIT',429)
                if w['active']>=concurrency:raise GatewayError('BUSY',429)
            self._audit(db,meta,reserve_extra=1)
            db.execute('INSERT INTO calls VALUES (?,?,?,NULL,?,?,0,NULL,0)',(meta.request_id,key_id,self.clock(),'reserved',amount_nano))
        return meta.request_id
    def finish(self,request_id,cost_nano,usage,state,elapsed_ms):
        if state not in ('completed','unknown','failed','output_blocked') or type(cost_nano)!=int or cost_nano<0:raise ValueError('settlement')
        with self.transaction() as db:
            row=db.execute('SELECT * FROM calls WHERE id=?',(request_id,)).fetchone()
            if row is None:raise ValueError('reservation missing')
            if row['state']!='reserved':return
            if state=='unknown':cost_nano=row['reserve']
            if cost_nano>row['reserve']:db.execute("INSERT OR REPLACE INTO meta VALUES ('halt','overrun')")
            old=db.execute("SELECT event FROM audit WHERE json_extract(event,'$.request_id')=? ORDER BY id LIMIT 1",(request_id,)).fetchone()
            meta=EventMeta.model_validate_json(old[0]);meta=meta.model_copy(update={'state':state})
            self._audit(db,meta,reserve_extra=-1)
            db.execute('UPDATE calls SET settled=?,state=?,cost=?,usage=?,elapsed_ms=? WHERE id=?',
                       (self.clock(),state,cost_nano,usage.model_dump_json() if usage else None,elapsed_ms,request_id))
    def record(self,meta):
        with self.transaction() as db:
            own=db.execute("SELECT 1 FROM calls WHERE id=? AND state='reserved'",(meta.request_id,)).fetchone()
            self._audit(db,meta,reserve_extra=-1 if own else 0)
    def recover(self):
        with self.transaction() as db:
            db.execute("UPDATE calls SET state='unknown',cost=reserve,settled=? WHERE state='reserved'",(self.clock(),))
    def limits(self,key_id):
        with self.transaction() as db:
            count=db.execute('SELECT count(*) FROM attempts WHERE key_id=? AND ts>?',(key_id,self.clock()-60)).fetchone()[0]
            return {'key':self._window(db,key_id,1800,100_000_000),'global':self._window(db,None,86400,1_000_000_000),
                    'rate':{'used':count,'limit':10},'halted':bool(db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone()),'currency':'USD'}
    def cleanup(self):
        with self.transaction() as db:
            db.execute('DELETE FROM audit WHERE ts<? AND json_extract(event,\'$.request_id\') NOT IN (SELECT id FROM calls WHERE state=\'reserved\')',(self.clock()-7*86400,))
            db.execute("DELETE FROM calls WHERE state!='reserved' AND settled<?",(self.clock()-7*86400,))
            db.execute('DELETE FROM attempts WHERE ts<=?',(self.clock()-60,))
    def events(self):
        with self.transaction() as db:
            result=[]
            for row in db.execute('SELECT ts,event FROM audit ORDER BY id'):
                event=EventMeta.model_validate_json(row['event']).model_dump(exclude_none=True)
                event['timestamp']=row['ts']
                call=db.execute('SELECT cost,usage,elapsed_ms,state FROM calls WHERE id=?',(event['request_id'],)).fetchone()
                if call:
                    event.update(cost_nano=call['cost'],usage=json.loads(call['usage']) if call['usage'] else None,elapsed_ms=call['elapsed_ms'],call_state=call['state'])
                result.append(event)
            return result
