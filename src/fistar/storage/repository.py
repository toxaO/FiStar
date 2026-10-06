import json
import sqlite3
from pathlib import Path
from dataclasses import asdict
from datetime import datetime,timezone
from fistar.core.models import *

def connect_database(path: Path) -> sqlite3.Connection:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(path)
    connection.execute('PRAGMA foreign_keys=ON')
    # New versioned tables never modify the legacy analyses table.
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS devices_v1(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS limits_v1(device TEXT NOT NULL,axis TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(device,axis));
        CREATE TABLE IF NOT EXISTS measurements_v1(id TEXT PRIMARY KEY,created_utc TEXT NOT NULL,device TEXT NOT NULL,axis TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS measurements_v1_filter ON measurements_v1(device,axis,created_utc);
    """)
    return connection

def utc(value):
    date=datetime.fromisoformat(value)
    if date.tzinfo is None: raise ValueError('日時にはタイムゾーンが必要です')
    return date.astimezone(timezone.utc).isoformat()

def metric_from_dict(d):
    return MetricResult(d['unit'],Circle(Point(**d['circle']['center']),d['circle']['radius']),Point(**d['laser_delta']),d['laser_distance'])

def centroid_from_dict(d):
    if not d: return None
    return CentroidMetric(d['unit'],Point(**d['center']),Point(**d['laser_delta']),d['laser_distance'],
        tuple(Intersection(tuple(p['spoke_ids']),Point(**p['point']),p['distance']) for p in d['intersections']),
        d['max_distance'],tuple(tuple(pair) for pair in d.get('skipped_pairs',())),tuple(d.get('warnings',())))

def measurement_from_dict(d):
    r=d['result']
    result=AnalysisResult(metric_from_dict(r['pixels']),metric_from_dict(r['physical']) if r['physical'] else None,tuple(r['active_spoke_ids']),centroid_from_dict(r.get('centroid_pixels')),centroid_from_dict(r.get('centroid_physical')),r.get('centroid_error',''),r.get('center_method','minimax'))
    return Measurement(d['id'],d['created_at'],d['device'],d['axis'],d['image_name'],result,Limits(**d['limits']),Judgment(**d['judgment']),d['snapshot'])

def save_measurement(connection,measurement: Measurement) -> str:
    payload=json.dumps(asdict(measurement),ensure_ascii=False,allow_nan=False)
    with connection:
        connection.execute('INSERT OR IGNORE INTO devices_v1 VALUES (?)',(measurement.device,))
        connection.execute('INSERT INTO measurements_v1 VALUES (?,?,?,?,?)',(measurement.id,utc(measurement.created_at),measurement.device,measurement.axis,payload))
    return measurement.id

def list_measurements(connection,device=None,axis=None,since=None,until=None) -> tuple[Measurement,...]:
    conditions=[]; args=[]
    for key,value in [('device',device),('axis',axis),('created_utc >=',utc(since) if since else None),('created_utc <',utc(until) if until else None)]:
        if value is not None:
            conditions.append(key+' ?' if key.endswith(('>=','<')) else key+' = ?'); args.append(value)
    query='SELECT payload FROM measurements_v1'+(' WHERE '+' AND '.join(conditions) if conditions else '')+' ORDER BY created_utc DESC,id DESC'
    return tuple(measurement_from_dict(json.loads(row[0])) for row in connection.execute(query,args))

def set_limits(connection,device,axis,limits):
    if not device.strip() or axis not in ('gantry','collimator','couch'): raise ValueError('装置名・軸が必要です')
    with connection:
        connection.execute('INSERT OR IGNORE INTO devices_v1 VALUES (?)',(device,))
        connection.execute('INSERT INTO limits_v1 VALUES (?,?,?) ON CONFLICT(device,axis) DO UPDATE SET payload=excluded.payload',(device,axis,json.dumps(asdict(limits),allow_nan=False)))

def get_limits(connection,device,axis):
    row=connection.execute('SELECT payload FROM limits_v1 WHERE device=? AND axis=?',(device,axis)).fetchone()
    return Limits(**json.loads(row[0])) if row else Limits()

def delete_measurement(connection,id):
    with connection: connection.execute('DELETE FROM measurements_v1 WHERE id=?',(id,))

def list_devices(connection):
    return tuple(r[0] for r in connection.execute('SELECT name FROM devices_v1 ORDER BY name'))
