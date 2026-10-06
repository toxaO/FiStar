import sqlite3
from dataclasses import replace
from datetime import datetime,timezone
import pytest
from fistar.storage.repository import connect_database,save_measurement,list_measurements,set_limits,get_limits,delete_measurement
from fistar.core.models import *

@pytest.fixture
def measurement():
    m=MetricResult('px',Circle(Point(1.23456789,2),.123456789),Point(1,2),2.2360679)
    return Measurement('one','2026-10-01T09:00:00+09:00','装置A','gantry','画像.tif',AnalysisResult(m,None,('line',)),Limits('mm'),Judgment('unset','unset'),{'schema_version':1,'spokes':[{'origin':'manual'}]})

def test_old_table_kept_and_precision(tmp_path,measurement):
    p=tmp_path/'db.sqlite'
    c=sqlite3.connect(p); c.execute('CREATE TABLE analyses(marker TEXT)'); c.execute("INSERT INTO analyses VALUES ('keep')"); c.commit(); c.close()
    c=connect_database(p)
    save_measurement(c,measurement)
    assert c.execute('SELECT marker FROM analyses').fetchone()[0]=='keep'
    assert list_measurements(c)==(measurement,)
    set_limits(c,'装置A','gantry',Limits('px',2,3))
    assert get_limits(c,'装置A','gantry')==Limits('px',2,3)
    assert list_measurements(c)[0].limits==Limits('mm')
    c.close()

def test_filters_timezone_and_delete(tmp_path,measurement):
    c=connect_database(tmp_path/'db.sqlite')
    save_measurement(c,measurement)
    save_measurement(c,replace(measurement,id='two',axis='couch',created_at='2026-09-30T20:00:00-05:00'))
    assert list_measurements(c)[0].id=='two'
    assert len(list_measurements(c,axis='gantry'))==1
    assert not list_measurements(c,device='other')
    assert len(list_measurements(c,since='2026-10-01T00:30:00+00:00'))==1
    delete_measurement(c,'one'); assert len(list_measurements(c))==1
    c.close()
