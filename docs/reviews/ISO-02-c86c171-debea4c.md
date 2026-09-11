# Review — ISO-02 at c86c171 + debea4c (seat 3/3)

**Reviewer:** MacBook seat (grok-4.6), session 01a08fce, only Grok seat.  
**Reviewed:** `c86c17152833c1b56ab2d73a8715f3928ed11e28` + `debea4c02cece3639220849171797b852a5c0cee`  
**Verdict:** **ACCEPT** both.

## 3/3 file (`tests/unit/test_sqlite_store.py`)

The old `not (DEFAULT_STATE_ROOT/"peb.sqlite").exists()` required the operator database to be absent. After LIVE-01 that is false on this machine. `operator_state.unchanged()` is the right assertion: isolated `state_root` may create a db; the operator root must match its pre-session snapshot whether that snapshot is empty or populated. **Pass.**

## Guard (1/3 `tests/conftest.py`)

Session autouse: snapshot then `PEB_STATE_ROOT` redirect to a temp root, then compare. Absent files are a valid fingerprint (`None`). Protected list:

`peb.sqlite`, `-wal`, `-shm`, `keys/development_local_hmac.key`, `operator.secret`, `supervisor.lock`, `inference.lock`.

**Store write set (this lane):** `SqliteRepository.open` writes `peb.sqlite` (+ WAL/SHM) and `keys/development_local_hmac.key`. Those are covered. Checkpoints/receipts live inside the sqlite file.

**Optional extra, not a CHANGES:** `peb.sqlite-journal` if a connection ever leaves WAL; extra files under `keys/` other than the hmac key are not fingerprinted (only the named key file). `<root>` directory fingerprint catches new *top-level* names. Not required for ACCEPT.

## debea4c

The guard catching service tests taking the MacBook-wide `inference.lock` is the proof it works. Temp lock path in those tests is correct. **Pass.**
