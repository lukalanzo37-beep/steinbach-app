from __future__ import annotations
import sqlite3, zipfile
from datetime import datetime
from pathlib import Path
from db import DB_PATH

ROOT=Path(__file__).resolve().parent
UPLOADS=ROOT/'uploads'
BACKUPS=ROOT/'backups'
BACKUPS.mkdir(exist_ok=True)
stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
tmp=BACKUPS/f'steinbach-{stamp}.db'
out=BACKUPS/f'steinbach-backup-{stamp}.zip'

src=sqlite3.connect(DB_PATH)
dst=sqlite3.connect(tmp)
with dst:
    src.backup(dst)
dst.close(); src.close()

with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    z.write(tmp,'data/steinbach.db')
    if UPLOADS.exists():
        for f in UPLOADS.rglob('*'):
            if f.is_file() and f.name != '.gitkeep':
                z.write(f,Path('uploads')/f.relative_to(UPLOADS))
tmp.unlink(missing_ok=True)
print(out)
