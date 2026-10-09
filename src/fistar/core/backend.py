"""Prepare the analysis backend once per process, with a reusable font cache."""
import atexit
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import threading
import time

_lock=threading.Lock()
_prepared=None

@dataclass(frozen=True)
class BackendInfo:
    cache_path: str
    persistent: bool
    reused: bool
    seconds: float


def cache_identity():
    executable=Path(sys.executable).resolve()
    location=str(executable if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])
    stamp=executable.stat()
    payload=[version('matplotlib'),platform.python_version(),platform.system(),platform.machine(),location,
             (stamp.st_size,stamp.st_mtime_ns) if getattr(sys,'frozen',False) else 'source']
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()[:24]


def configure_cache(root):
    """Fall back to a private temporary cache when persistent storage is unusable."""
    cache=Path(root)/'matplotlib'/cache_identity()
    try:
        cache.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryFile(dir=cache):pass
        files=list(cache.glob('fontlist-*.json'))
        for path in files:
            data=json.loads(path.read_text())
            if not isinstance(data,dict) or not isinstance(data.get('ttflist'),list):raise ValueError('Invalid font cache')
        persistent=True;reused=bool(files)
    except (OSError,ValueError,UnicodeError):
        cache=Path(tempfile.mkdtemp(prefix='fistar-matplotlib-'))
        atexit.register(shutil.rmtree,cache,ignore_errors=True)
        persistent=False;reused=False
    os.environ['MPLCONFIGDIR']=str(cache)
    return cache,persistent,reused


def prepare_backend(root):
    global _prepared
    with _lock:
        if _prepared is not None:return _prepared
        started=time.perf_counter()
        cache,persistent,reused=configure_cache(root)
        # Runs after PyInstaller's temporary MPLCONFIGDIR hook, before matplotlib imports.
        from pylinac.starshot import StarProfile
        from pylinac.core.image import ArrayImage
        from pylinac.core.geometry import Point
        import matplotlib.font_manager
        _prepared=BackendInfo(str(cache),persistent,reused,time.perf_counter()-started)
        return _prepared
