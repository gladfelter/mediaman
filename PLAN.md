# Photo Sync Client — Plan

## Overview

Port the Windows photo collection client (`photocoll.py`) from Python 2 to
Python 3 with modern dependencies, making it testable and deployable on
current Windows machines.

The client watches a local Pictures directory and syncs new photos to the
home server's Samba staging share, where `photoman.py` archives them into
the permanent photo library.

---

## Architecture Context

```
[Windows laptop]                    [Ubuntu server 192.168.8.244]
                                    
photocoll.py                         photoman.py (cron: hourly)
  ↓                                     ↓
  scans ~/Pictures                      reads /library/photo_staging
  checks local state (json)             MD5+size dedup against /library/photos
  copies new files to:                  archives to /library/photos/YYYY/MM_Name/
    \\192.168.8.244\photo_staging  →    deletes staging files (--del_src)
                                        scans for missing (cron: 01:00 daily)

[Windows desktop]                   
(same client, same staging share)
```

### Existing server (fully operational)
- **OS**: Ubuntu 26.04 LTS, hostname `david-A75MG`
- **IP**: 192.168.8.244
- **Photo archive**: `/library/photos/` (150GB, year/month structure)
- **Staging share**: Samba `\\192.168.8.244\photo_staging` → `/library/photo_staging`
- **Cron**: photoman runs hourly (archives from staging), 01:00 (scan missing), 02:00 (EXIF fixer)
- **Test suite**: `mediaman/run_tests.sh` — 25 tests, 1 skip

### Existing client (Python 2, needs porting)
- `mediaman/photocoll.py` — legacy code, Windows-only, uses `ctypes` Win32, `pickle`, `gflags`
- `mediaman/photocoll_test.py` — existing tests (unported, Windows-only)
- `mediaman/library_client.py` — obsolete RPC client (never used in practice)
- `mediaman/library_server.py` — obsolete RPC server (never used in practice)

---

## Requirements

### Functional
- [ ] **F1**: Scan `~/Pictures` for new photos since last collection
- [ ] **F2**: Copy new photos to a configurable staging directory (Samba share path)
- [ ] **F3**: Maintain local state (JSON) tracking last-collection timestamp per source directory
- [ ] **F4**: Skip files matching a configurable list of ignored extensions
- [ ] **F5**: Handle filename collisions at destination (append `_1`, `_2`)
- [ ] **F6**: Run as a single-shot script (schedule via Task Scheduler, not a daemon)
- [ ] **F7**: Operate cross-platform in test mode (POSIX paths in tests, Windows paths in production)

### Non-functional
- [ ] **NF1**: Python 3.10+ (available via `winget install python` on Windows, python.org, or WSL)
- [ ] **NF2**: No compiled dependencies — pure Python + stdlib
- [ ] **NF3**: Exit code 0 on success, non-zero on failure (for Task Scheduler monitoring)
- [ ] **NF4**: Log to stderr with timestamps; also write to a log file

---

## Critical User Journeys

### Journey 1: First run on a new machine
```
Given a Windows PC with photos in ~/Pictures
And the client has never run before
When the user runs: python photocoll.py --staging_dir \\192.168.8.244\photo_staging
Then ALL photos in ~/Pictures are copied to the staging share
And a state file is created recording the collection timestamp
And no files are overwritten at the destination
```

### Journey 2: Subsequent incremental run
```
Given the client has run before (state file exists)
And new photos were added to ~/Pictures since last run
When the user runs the client again
Then only the new photos are copied to staging
And existing photos are skipped
And the state file is updated with the new timestamp
```

### Journey 3: Duplicate filename handling
```
Given IMG_0001.jpg already exists in the staging directory
And a different file also named IMG_0001.jpg appears in ~/Pictures
When the client runs
Then the new file is copied as IMG_0001_1.jpg (not overwriting the original)
And the copy is byte-identical to the source
```

### Journey 4: Ignored extensions
```
Given ~/Pictures contains photo.jpg, notes.txt, and thumbs.db
And the client is configured to ignore ['.txt', '.db', '.ini']
When the client runs
Then only photo.jpg is copied
And notes.txt and thumbs.db are skipped
```

### Journey 5: Network failure
```
Given the staging Samba share is unreachable
When the client attempts to copy files
Then the operation fails with a non-zero exit code
And the state file is NOT updated (no lost tracking on failure)
```

### Journey 6: Staging directory doesn't exist
```
Given the staging directory path does not exist
When the client runs
Then the directory is created (with parents)
And files are copied successfully
```

---

## Design Decisions

| Decision | Rationale |
|---|---|
| JSON state instead of pickle | Human-readable, debuggable, no code-execution risk |
| `pathlib` instead of `ctypes` Win32 | Cross-platform, testable on Linux, Windows `~/Pictures` resolves correctly on both |
| `argparse` instead of `gflags` | Stdlib, same decision made for photoman.py port |
| Single-shot, not daemon | Simpler to schedule via Task Scheduler; no process management |
| Copy-then-update-state ordering | If copy fails mid-way, state isn't updated; re-run picks up the missing files |
| `shutil.copy2` for file copy | Preserves metadata (timestamps) like the original |
| No RPC dedup in client | Server-side photoman.py handles MD5+size dedup; client just pushes everything |

---

## Testing Plan (TDD)

### Test pyramid
```
        ┌──────────┐
        │   E2E    │  1 test:  full pipeline with temp dirs
        ├──────────┤
        │Integration│  3 tests: filesystem ops, state read/write, collision handling
        ├──────────┤
        │   Unit   │  10 tests: find_new_photos, state tracking, ignore logic, path resolution
        └──────────┘
```

### Test file: `test_photocoll.py` (replaces `photocoll_test.py`)

**Phase 1: Unit tests (write first, no implementation)**

| Test | What it verifies | Mock strategy |
|---|---|---|
| `test_find_new_photos_none` | Returns empty list when state is current | Mock `os.walk`, `os.path.getmtime` |
| `test_find_new_photos_some` | Returns only files modified after last collection | Mock `os.walk`, `os.path.getmtime` |
| `test_find_new_photos_ignores_extensions` | Filters out ignored extensions | Mock `os.walk`, `os.path.getmtime` |
| `test_find_new_photos_handles_mtime_none` | Gracefully handles files with unreadable mtime | Mock `os.path.getmtime` raising OSError |
| `test_collection_state_new` | Creates fresh state when no file exists | Temp file, monkeypatch |
| `test_collection_state_update` | Updates timestamp after successful run | Temp file, monkeypatch |
| `test_collection_state_preserves_on_copy_failure` | Doesn't update state if copies fail | Mock copy raising exception |
| `test_copy_file_renames_on_collision` | Appends `_1`, `_2` when dest exists | Temp dirs, real files |
| `test_copy_file_no_collision` | Copies directly when no conflict | Temp dirs, real files |
| `test_resolve_staging_dir_creates_missing` | Creates staging dir if it doesn't exist | Temp dirs |

**Phase 2: Integration tests (write against real temp dirs)**

| Test | What it verifies |
|---|---|
| `test_full_pipeline_no_prior_state` | Create temp source dir with files → run collect → verify copies exist in staging |
| `test_full_pipeline_incremental` | Run once, add more files, run again → only new files copied |
| `test_full_pipeline_collision` | File exists in staging, same-name file in source → renamed copy |

**Phase 3: E2E test**
| Test | What it verifies |
|---|---|
| `test_end_to_end_with_tempdirs` | Full pipeline: scan → filter → copy → state update → verify idempotent re-run copies nothing |

### Test constraints
- All file I/O tests use `tempfile.TemporaryDirectory` — cleaned up automatically
- No Windows-specific paths in tests; use `pathlib.Path` objects
- Tests run on Linux (WSL) and Windows
- Run with `python -m pytest test_photocoll.py -v` (add `pytest` as dev dependency)

### TDD sequence
1. Write `test_find_new_photos_*` → fail
2. Implement `find_new_photos()` → pass
3. Write `test_collection_state_*` → fail
4. Implement `CollectionState` class → pass
5. Write `test_copy_file_*` → fail
6. Implement `copy_file()` → pass
7. Write integration tests → fail
8. Implement `collect_photos()` orchestration → pass
9. Write E2E test → fail
10. Implement `main()` with argparse → pass

---

## Implementation Plan

### Files to create/modify
```
mediaman/
├── photocoll.py          # Ported client (rewrite)
├── test_photocoll.py     # New test file (replaces photocoll_test.py)
├── photocoll_test.py     # Delete (replaced by test_photocoll.py)
├── requirements-dev.txt  # pytest (dev dependency)
└── run_tests.sh          # Update to include new test file
```

### Module: `photocoll.py`

**Classes:**

1. `CollectionState` — Manages the JSON state file
   - `__init__(state_path: Path)` — loads existing or creates empty
   - `get_last_collection(src_dir: Path) -> float` — returns epoch timestamp
   - `set_last_collection(src_dir: Path, timestamp: float)` — updates in memory
   - `save()` — writes to disk

2. Free functions:
   - `find_new_photos(src_dir, last_collection, ignore_extensions) -> list[Path]`
   - `copy_files(files, dest_dir) -> list[Path]` — returns list of successfully copied dest paths
   - `collect_photos(src_dir, staging_dir, ignore_extensions)` — orchestrates the above
   - `main()` — argparse entry point

**Dependencies:** `pathlib`, `argparse`, `json`, `logging`, `shutil` — all stdlib.

### Deployment
- Install Python 3.10+ on Windows (`winget install Python.Python.3.12` or python.org)
- Clone or copy `mediaman/` to `C:\Users\<user>\mediaman\`
- Create Windows Task Scheduler task:
  - Trigger: At log on, repeat every 4 hours
  - Action: `python C:\Users\<user>\mediaman\photocoll.py --staging_dir "\\192.168.8.244\photo_staging"`
  - Start in: `C:\Users\<user>\mediaman\`
- State file location: `%LOCALAPPDATA%\mediaman\collection_state.json` (auto-detected via `platformdirs` or `pathlib`)

---

## Future: Google Photos Sync

Out of scope for this plan. After the client is working:

1. One-time bulk: Google Takeout → extract → point `photoman --src_dir` at the dump
2. Ongoing: Evaluate `rclone` (Google Photos backend) running on the Ubuntu server, pulling to staging

---

## Context for Next Session

- **Repo**: `~/projects/mediaman` (WSL), `git@github.com:gladfelter/mediaman.git`
- **Branch**: `master` (Python 3 port already merged, 25 tests pass)
- **Server**: `david@192.168.8.244` (Ubuntu 26.04), photo archive at `/library/photos`, Samba staging at `photo_staging`
- **Test runner**: `cd mediaman && ./run_tests.sh` (uses `python3 -m unittest discover`)
- **Dependencies**: python3-pil, python3-piexif (server only); client uses stdlib only
- **This plan**: `PLAN.md` at repo root
