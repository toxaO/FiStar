"""Build on the target OS using the project virtual environment."""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--platform',choices=['macos','windows'],required=True)
    parser.add_argument('--clean',action='store_true',help='Clear PyInstaller caches before building')
    args=parser.parse_args()
    expected='Darwin' if args.platform=='macos' else 'Windows'
    if platform.system()!=expected:parser.error(f'{args.platform} builds must run on {expected}.')
    try:import PyInstaller
    except ImportError:parser.error('Install build dependencies: python -m pip install -e ".[build]"')
    output=ROOT/'dist'/args.platform
    data_root=output/'data' if args.platform=='macos' else output/'FiStar/data'
    if data_root.exists() and any(data_root.iterdir()):
        raise RuntimeError('Existing data directory contains records. Back it up and move it before building; it will not be overwritten.')
    work=ROOT/'build'/args.platform
    work.mkdir(parents=True,exist_ok=True)
    icon=ROOT/'src/fistar/gui/assets'/('fistar.icns' if args.platform=='macos' else 'fistar.ico')
    if args.platform=='macos':
        from PIL import Image
        with Image.open(ROOT/'src/fistar/gui/assets/fistar.png') as image:image.convert('RGBA').save(icon,format='ICNS')
    mode='--onedir'
    assets=ROOT/'src/fistar/gui/assets'
    if any(p.is_file() and p.suffix.lower() not in {'.png','.svg','.ico','.icns'} for p in assets.rglob('*')):
        raise RuntimeError('Unexpected file in app assets; only explicit icon/image formats may be bundled.')
    command=[sys.executable,'-m','PyInstaller','--noconfirm',mode,'--windowed','--name','FiStar','--paths',str(ROOT/'src'),'--distpath',str(output),'--workpath',str(work/'work'),'--specpath',str(work),'--icon',str(icon),'--add-data',f'{ROOT / "src/fistar/gui/assets"}:fistar/gui/assets','--recursive-copy-metadata','pylinac','--exclude-module','tkinter']
    if args.platform=='macos':command+=['--osx-bundle-identifier','com.toxao.fistar']
    if args.clean:command.append('--clean')
    command.append(str(ROOT/'scripts/launch.py'))
    env=dict(os.environ,PYINSTALLER_CONFIG_DIR=str(ROOT/'build/pyinstaller-cache'),MPLCONFIGDIR=str(ROOT/'build/matplotlib-cache'))
    subprocess.run(command,cwd=ROOT,env=env,check=True)
    for name in ['LICENSE','THIRD_PARTY_NOTICES.md']:
        shutil.copy2(ROOT/name,output/name)
    shutil.copytree(ROOT/'licenses',output/'licenses',dirs_exist_ok=True)
    shutil.copy2(ROOT/'docs/FiStar-user-manual.pdf',output/'FiStar-user-manual.pdf')
    forbidden=[p for p in output.rglob('*') if p.is_file() and (p.suffix.lower() in {'.sqlite','.sqlite3'} or p.name.startswith('fistar-preferences.ini'))]
    if forbidden:raise RuntimeError(f'Unexpected user database/settings in build: {forbidden}')
    data_root=output/'data' if args.platform=='macos' else output/'FiStar/data'
    data_root.mkdir(parents=True,exist_ok=True)
    if any(data_root.iterdir()):raise RuntimeError('Build data directory is not empty. Move existing local data before making a release.')
    print(f'Build complete: {output}')
    print('License notices copied. Audit the actual bundled libraries before release.')

if __name__=='__main__':main()
