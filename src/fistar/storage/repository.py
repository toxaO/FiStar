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
    axes_exist=connection.execute("SELECT 1 FROM sqlite_master WHERE name='axes_v1'").fetchone()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS axes_v1(id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,top TEXT,bottom TEXT,left_label TEXT,right_label TEXT);
        CREATE TABLE IF NOT EXISTS devices_v1(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS limits_v1(device TEXT NOT NULL,axis TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(device,axis));
        CREATE TABLE IF NOT EXISTS measurements_v1(id TEXT PRIMARY KEY,created_utc TEXT NOT NULL,device TEXT NOT NULL,axis TEXT NOT NULL,payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS measurements_v1_filter ON measurements_v1(device,axis,created_utc);
    """)
    if not axes_exist:
        with connection:connection.executemany("INSERT INTO axes_v1 VALUES (?,?,?,?,?,?)",[("gantry","ガントリ","0°","180°","270°","90°"),("collimator","コリメータ","G","T","270°","90°"),("couch","カウチ","H","F","L","R")])
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
    # Legacy records store displacement Y positive downward; normalize in memory only.
    if d['snapshot'].get('laser_delta_y_positive')!='up':
        from dataclasses import replace
        def upward(metric):
            return replace(metric,laser_delta=Point(metric.laser_delta.x,-metric.laser_delta.y)) if metric else None
        result=replace(result,pixels=upward(result.pixels),physical=upward(result.physical),centroid_pixels=upward(result.centroid_pixels),centroid_physical=upward(result.centroid_physical))
        d=dict(d);d['snapshot']=dict(d['snapshot'],laser_delta_y_positive='up')
    return Measurement(d['id'],d['created_at'],d['device'],d['axis'],d['image_name'],result,Limits(**d['limits']) if d.get('limits') else Limits(),Judgment(**d['judgment']) if d.get('judgment') else Judgment('not_evaluated','not_evaluated'),d['snapshot'])

def save_measurement(connection,measurement: Measurement) -> str:
    data=asdict(measurement)
    if measurement.snapshot.get('judgment_enabled') is False:
        data.pop('limits',None);data.pop('judgment',None)
    payload=json.dumps(data,ensure_ascii=False,allow_nan=False)
    with connection:
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


def add_device(connection,name):
    name=name.strip()
    if not name:raise ValueError('装置名を入力してください')
    try:
        with connection:connection.execute('INSERT INTO devices_v1(name) VALUES (?)',(name,))
    except sqlite3.IntegrityError as error:raise ValueError('同じ装置名が登録されています') from error
    return name

def remove_device(connection,name):
    with connection:connection.execute('DELETE FROM devices_v1 WHERE name=?',(name,))

def list_record_devices(connection):
    return tuple(row[0] for row in connection.execute('SELECT name FROM devices_v1 UNION SELECT DISTINCT device FROM measurements_v1 ORDER BY 1'))


def list_axes(connection):
    return [dict(zip(('id','name','top','bottom','left','right'),row)) for row in connection.execute('SELECT * FROM axes_v1 ORDER BY rowid')]

def save_axis(connection,key,name,top,bottom,left,right):
    from uuid import uuid4
    name=name.strip()
    if not name:raise ValueError('軸名を入力してください')
    key=key or str(uuid4())
    try:
        with connection:connection.execute('INSERT INTO axes_v1 VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,top=excluded.top,bottom=excluded.bottom,left_label=excluded.left_label,right_label=excluded.right_label',(key,name,top.strip(),bottom.strip(),left.strip(),right.strip()))
    except sqlite3.IntegrityError as error:raise ValueError('同じ軸名が登録されています') from error
    return key

def remove_axis(connection,key):
    if len(list_axes(connection))<=1:raise ValueError('回転軸は少なくとも1件残してください')
    with connection:connection.execute('DELETE FROM axes_v1 WHERE id=?',(key,))
