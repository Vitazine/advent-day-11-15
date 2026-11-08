"""Durable admission, reservations and sanitized audit in a single SQLite transaction."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

IP_CAP = 100_000_000
GLOBAL_CAP = 1_000_000_000

class LimitError(Exception):
    def __init__(self, code): self.code = code

class Ledger:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=DELETE;
            PRAGMA secure_delete=ON;
            CREATE TABLE IF NOT EXISTS attempts(ip TEXT, ts REAL);
            CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip,ts);
            CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY, ip TEXT, ts REAL, settled REAL,
                state TEXT, reserve INTEGER, cost INTEGER, prompt TEXT,
                response TEXT, categories TEXT, usage TEXT, elapsed_ms INTEGER DEFAULT 0);
            CREATE INDEX IF NOT EXISTS events_ip ON events(ip,settled);
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
            ''')
        self.path.chmod(0o600)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        db.execute('PRAGMA synchronous=FULL')
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def attempt(self, ip):
        now = self.clock()
        with self.transaction() as db:
            db.execute('DELETE FROM attempts WHERE ts<=?', (now-60,))
            count = db.execute('SELECT count(*) FROM attempts WHERE ip=?', (ip,)).fetchone()[0]
            if count >= 10: raise LimitError('RATE_LIMIT')
            db.execute('INSERT INTO attempts VALUES (?,?)', (ip,now))

    def _window(self, db, ip, seconds, cap):
        now = self.clock()
        query = "SELECT state,reserve,cost,settled FROM events WHERE (state='reserved' OR settled>?)"
        params = [now-seconds]
        if ip is not None:
            query += ' AND ip=?'; params.append(ip)
        rows = db.execute(query, params).fetchall()
        reserved = sum(r['reserve'] for r in rows if r['state']=='reserved')
        spent = sum(r['cost'] for r in rows if r['state']!='reserved')
        unknown = sum(r['cost'] for r in rows if r['state']=='unknown')
        releases = [r['settled']+seconds for r in rows if r['settled'] and r['cost']]
        return dict(cap_nano=cap, spent_nano=spent, reserved_nano=reserved,
                    unknown_nano=unknown, remaining_nano=max(0,cap-spent-reserved),
                    next_release_at=min(releases) if releases else None, window_seconds=seconds)

    def reserve(self, ip, amount, safe_prompt, categories):
        if type(amount) is not int or amount <= 0: raise ValueError('Invalid reserve')
        rid, now = uuid.uuid4().hex, self.clock()
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone():
                raise LimitError('SAFETY_HALT')
            for target, seconds, cap in ((ip,1800,IP_CAP),(None,86400,GLOBAL_CAP)):
                if self._window(db,target,seconds,cap)['remaining_nano'] < amount:
                    raise LimitError('BUDGET_LIMIT')
            if db.execute("SELECT count(*) FROM events WHERE state='reserved' AND ip=?",(ip,)).fetchone()[0]:
                raise LimitError('BUSY')
            if db.execute("SELECT count(*) FROM events WHERE state='reserved'").fetchone()[0] >= 2:
                raise LimitError('BUSY')
            db.execute('INSERT INTO events(id,ip,ts,state,reserve,cost,prompt,response,categories,usage) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (rid,ip,now,'reserved',amount,0,safe_prompt,'',json.dumps(list(categories)), '{}'))
        return rid

    def finish(self, rid, cost, safe_response, categories, usage, state, elapsed_ms=0):
        if state not in ('completed','output_blocked','unknown') or type(cost) is not int or cost<0:
            raise ValueError('Invalid settlement')
        with self.transaction() as db:
            row=db.execute("SELECT reserve FROM events WHERE id=? AND state='reserved'",(rid,)).fetchone()
            if row is None: raise ValueError('Reservation absent')
            if state=='unknown': cost=row['reserve']
            if cost>row['reserve']:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('halt','usage_exceeded_reserve')")
            db.execute('UPDATE events SET settled=?,state=?,cost=?,response=?,categories=?,usage=?,elapsed_ms=? WHERE id=?',
                       (self.clock(),state,cost,safe_response,json.dumps(list(categories)),json.dumps(usage),elapsed_ms,rid))

    def record(self, ip, state, safe_prompt, categories):
        with self.transaction() as db:
            db.execute('INSERT INTO events(id,ip,ts,settled,state,reserve,cost,prompt,response,categories,usage) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (uuid.uuid4().hex,ip,self.clock(),self.clock(),state,0,0,safe_prompt,'',json.dumps(list(categories)),'{}'))

    def recover(self):
        with self.transaction() as db:
            db.execute("UPDATE events SET state='unknown',cost=reserve,settled=? WHERE state='reserved'",(self.clock(),))

    def limits(self, ip):
        with self.transaction() as db:
            row=db.execute('SELECT count(*),min(ts) FROM attempts WHERE ip=? AND ts>?',(ip,self.clock()-60)).fetchone()
            return dict(ip=self._window(db,ip,1800,IP_CAP), global_budget=self._window(db,None,86400,GLOBAL_CAP),
                        rate=dict(limit=10,used=row[0],remaining=max(0,10-row[0]),next_release_at=row[1]+60 if row[1] else None),
                        halted=bool(db.execute("SELECT 1 FROM meta WHERE key='halt'").fetchone()),
                        server_time=self.clock(),currency='USD', pricing='peak_upper_estimate')

    def cleanup(self):
        with self.transaction() as db:
            db.execute("DELETE FROM events WHERE state!='reserved' AND settled<?",(self.clock()-7*86400,))
            db.execute('DELETE FROM attempts WHERE ts<=?',(self.clock()-60,))
            # Trim only expired audit text, never budget-bearing records.
            size=db.execute('SELECT coalesce(sum(length(CAST(prompt AS BLOB))+length(CAST(response AS BLOB))),0) FROM events').fetchone()[0]
            if size > 20*1024*1024:
                db.execute("UPDATE events SET prompt='[RETENTION_LIMIT]',response='' WHERE state!='reserved' AND settled<?",(self.clock()-86400,))
                size=db.execute('SELECT coalesce(sum(length(CAST(prompt AS BLOB))+length(CAST(response AS BLOB))),0) FROM events').fetchone()[0]
                if size > 20*1024*1024: raise LimitError('AUDIT_FULL')

    def events(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM events ORDER BY ts')]
