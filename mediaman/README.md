# mediaman

Photo library management for the Gladfelter home server.

## Components

| Script | Where it runs | Purpose |
|---|---|---|
| `photoman.py` | Ubuntu server | Archives photos from staging into `/library/photos/`, deduplicates by MD5+size |
| `photocoll.py` | Windows client | Scans `~/Pictures` for new photos, copies them to the Samba staging share |
| `fix_gnexus_exif.py` | Ubuntu server | Fixes Galaxy Nexus ISO EXIF arrays (legacy, no-op on modern files) |
| `flipfix.py` | Ubuntu server | One-off Flip camera timestamp fix |

### Architecture

```
Windows PC [photocoll.py]          Ubuntu server 192.168.8.244
     │                                    │
     │  copies new photos to:             │
     └──→ \\192.168.8.244\photo_staging ──→ photoman.py (cron, hourly)
                                          │
                                          ├─ dedup (MD5 + file size)
                                          ├─ archive to /library/photos/YYYY/MM_Name/
                                          └─ delete staging files
```

## Running

### Server (Ubuntu)
```bash
cd mediaman
./run_tests.sh                          # 25 tests, all pass

# Manual run (normally cron handles this):
python3 photoman.py --src_dir /library/photo_staging --media_dir /library --group_name library_adm
```

### Client (Windows)
```bash
# Run from source:
python photocoll.py --staging_dir "\\192.168.8.244\photo_staging"

# Or use the pre-built .exe (see Release below):
photocoll.exe --staging_dir "\\192.168.8.244\photo_staging"
```

## Tests
```bash
./run_tests.sh          # All 25 tests
./run_tests.sh -v       # Verbose output
```

## Release

The Windows client is distributed as a standalone `.exe` built by GitHub Actions.

**To create a release:**

1. Bump the version in `photocoll.py` (optional)
2. Tag and push:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. GitHub Actions builds `photocoll.exe` (Windows VM, ~2 minutes)
4. Download from: **Actions → latest workflow run → Artifacts → photocoll.exe**

**To install on a Windows machine:**

1. Copy `photocoll.exe` to `C:\Users\<user>\mediaman\`
2. Open **Task Scheduler** → Create Task:
   - **Trigger**: At log on, repeat every 4 hours
   - **Action**: Start a program
   - **Program**: `C:\Users\<user>\mediaman\photocoll.exe`
   - **Arguments**: `--staging_dir "\\192.168.8.244\photo_staging"`
3. State is tracked in `%LOCALAPPDATA%\mediaman\collection_state.json`

No Python installation required on the client machine.
