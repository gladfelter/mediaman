# mediaman

Photo library management for the Gladfelter home server. Supports the full lifecycle: day-to-day collection from Windows clients, one-shot bulk imports (Google Takeout), and permanent archival with deduplication.

## Architecture

```
Windows PC [photocoll.py]          Ubuntu server <SERVER_IP>
     │                                    │
     │  copies new photos to:             │
     └──→ \\<SERVER_IP>\photo_staging ──→ photoman.py (cron, hourly)
                                          │
                                          ├─ MD5+size dedup against 30k+ photo DB
                                          ├─ archive to /library/photos/YYYY/MM_Name/
                                          └─ delete staging files (--del_src)
```

## Journeys

### Journey 1: Day-to-day photo collection

A family member takes photos on their Windows laptop. Those photos land in `~/Pictures`. The client detects them and pushes them to the server's staging share. The server picks them up on its hourly cron cycle and archives them.

**On the Windows client** (first-time setup, once per machine):

1. Download `photocoll.exe` from [the latest release](https://github.com/gladfelter/mediaman/releases/latest)
2. Copy it to `C:\Users\<user>\mediaman\`
3. Open **Task Scheduler** → Create Task:
   - **Trigger**: At log on, repeat every 4 hours
   - **Action**: Start a program
   - **Program**: `C:\Users\<user>\mediaman\photocoll.exe`
   - **Arguments**: `--staging_dir "\\<SERVER_IP>\photo_staging"`
4. State is tracked in `%LOCALAPPDATA%\mediaman\collection_state.json`

No Python installation required on the client machine. The `.exe` is a self-contained single file.

**What happens on each run:**

1. Scans `~/Pictures` recursively for files newer than the last collection
2. Skips ignored extensions (`.ini`, `.db` by default; configurable with `--ignore_extensions`)
3. Copies new files to the Samba staging share
4. If a filename already exists at the destination, renames the incoming file with `_1`, `_2`, etc. — never overwrites
5. Updates the state file only after a successful copy (if the network fails mid-copy, state is unchanged and the next run re-attempts)

**On the server** (already configured via cron):

```bash
# Manual run for debugging:
cd ~/mediaman
python3 mediaman/photoman.py \
  --src_dir /library/photo_staging \
  --media_dir /library \
  --group_name library_adm \
  --del_src
```

**What happens on each server run:**

1. Walks all files in the staging directory
2. For each file, computes MD5+size and checks the SQLite database
3. If already in the archive → deletes the staging copy (or skips if `--del_src` not set)
4. If new → reads EXIF date, computes destination path (`/library/photos/YYYY/MM_Name/filename`), copies, verifies hash, deletes staging copy
5. One corrupted file doesn't stop the whole run — it's logged and skipped

### Journey 2: Google Takeout import (one-time)

You're moving off Google Photos and want to bring your entire history into the local library.  The entire workflow runs on the Windows client — no server-side steps needed beyond the normal staging cron.

**Step 1: Export from Google**

1. Go to [takeout.google.com](https://takeout.google.com), deselect everything, select only **Google Photos**
2. Request export — Google emails you when it's ready
3. Download the `.zip` files and extract them to a folder on your Windows machine

**Step 2: Fix timestamps and copy to staging (single command)**

```cmd
photocoll.exe fix-takeout --src_dir C:\Users\<user>\Downloads\takeout --staging_dir "\\<SERVER_IP>\photo_staging" --delete_json
```

Or run from source:

```bash
python mediaman/photocoll.py fix-takeout --src_dir ~/Downloads/takeout --staging_dir \\<SERVER_IP>\photo_staging --delete_json
```

This does three things in one pass:
1. Reads `.json` sidecar files and restores correct capture dates (mtimes) for videos and EXIF-less photos
2. Finds all actual media files (skips `.json`, `.txt`, and other non-media)
3. Copies them to the Samba staging share

**Step 3: The server picks them up** on the next hourly cron cycle and archives into `/library/photos/`.

**What to expect:**

| File type | How the date is determined | Status |
|---|---|---|
| Photos with EXIF | `DateTimeOriginal` tag read directly | Works automatically |
| Videos | Mtime set from `.json` sidecar by `google_takeout_fix_mtimes.py` | Requires step 2 |
| Photos without EXIF | Mtime set from `.json` sidecar | Requires step 2 |
| `.json` sidecar files | Skipped by photoman; deleted by the fix script (`--delete_json`) | Harmless either way |

### Journey 3: Server maintenance and health checks

**Check library health:**

```bash
cd ~/mediaman
./run_tests.sh          # 62 tests — all should pass

# DB row count:
python3 -c "import sqlite3; print(sqlite3.connect('/library/media.db').execute('SELECT COUNT(*) FROM photos').fetchone()[0])"

# Disk usage:
du -sh /library/photos/
```

**Scan for missing photos** (files deleted from disk but still in the DB — e.g. after a disk failure):

```bash
python3 mediaman/photoman.py \
  --src_dir /library/photo_staging \
  --media_dir /library \
  --scan_missing
```

This removes DB entries for any photos that no longer exist on disk. It includes safety guards: refuses to run if the photos directory is empty or missing (to avoid wiping the DB after an unmounted disk).

**What's in the database:**

A SQLite database at `/library/media.db` with one table:

```sql
photos (
    id integer primary key,
    flags text,
    md5 varchar(32),
    size integer,
    description text,
    source_info text,
    archive_path text,
    timestamp integer,
    camera_make text,
    camera_model text
)
```

Each photo is indexed by MD5 hash + file size for collision-resistant dedup.

## Components

| Script | Where it runs | Purpose |
|---|---|---|
| `photoman.py` | Ubuntu server | Archives photos from staging into `/library/photos/`, deduplicates by MD5+size |
| `photocoll.py` | Windows client | Scans `~/Pictures` for new photos, copies to the Samba staging share. Also handles Google Takeout imports via `fix-takeout` subcommand. |
| `takeout_fixer.py` | Library (used by photocoll) | Fixes mtimes on Google Takeout exports by reading `.json` sidecars |
| `fix_gnexus_exif.py` | Ubuntu server | Fixes Galaxy Nexus ISO EXIF arrays (legacy, no-op on modern files) |
| `flipfix.py` | Ubuntu server | One-off Flip camera timestamp fix (requires `--dir` argument) |

## Tests

```bash
./run_tests.sh          # All 62 tests
./run_tests.sh -v       # Verbose output
```

17 media_common + 30 photocoll + 7 photoman + 8 google_takeout_fix_mtimes — all passing.

## Release

The Windows client is distributed as a standalone `.exe` built by GitHub Actions.

**To create a release:**

1. Bump the version in `photocoll.py` (optional)
2. Tag and push:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. GitHub Actions builds `photocoll.exe` (Windows VM, ~1 minute) and attaches it to a new [Release](https://github.com/gladfelter/mediaman/releases)
4. Download from: **Releases → latest → photocoll.exe**
