# Archive and student work

Collect, export, import, and restore student work. Modular parts registry.

## Timestamped export

Each Export creates a **new** folder (never overwrites):

```text
Biology-Period-3-20260720-154832/
  classroom.json
  student-data/
    alice/
      work.json
      makecode.tar.gz
```

Teacher picks the parent directory. Import picks one of these folders.

## Collect (REPORT)

Students do not listen for inbound TCP. Collect is pull-triggered:

1. Teacher clicks **Collect work** (`delivery.requestCollect`).
2. On the student's next agent hello, publisher sends `action: collect`.
3. Agent packs parts via `workpack.collectWorkBundle` and sends `report`.
4. Publisher stores under `/shared/classroom-work/<classroom_id>/<student_id>/`.
5. Same TCP session continues with `apply_work` (if queued) and/or config `apply`/`noop`.

## Parts registry (`workpack.py`)

| Part id | v1 | Pack | Unpack |
|---------|----|------|--------|
| makecode | yes | profile dir to makecode.tar.gz | atomic profile replace |
| library | no | add later | add later |

`work.json` lists parts with id, file, bytes, checksum.

To add a future app: register pack/unpack in `PARTS`. Do not invent new TCP actions.

### MakeCode restore rule (overwrite, not merge)

1. Rename live `makecodeProfile` to `makecodeProfile.bak-<utc>` if present.
2. Unpack tar into the live path.
3. Next MakeCode open sees the snapshot.

If the student deleted local work after Collect, restore puts the snapshot back.
If they made newer work after Collect, restore replaces it with the older snapshot. Collect again, then Export again for a new timestamped folder.

## Lesson files on apply

`enabled_lessons` in student-state are ids only. Lesson bodies live in `/shared/teacher-lessons/`.

On `apply`, publisher may attach `lessons_tar_b64`. Agent unpacks into `/shared/teacher-lessons` (1777 sticky) or `~/.local/share/cis4900/teacher-lessons` if not writable.

## Import / Export API

- `archive.exportClassroom(classroom_id, parent_dir)`
- `archive.importClassroom(path, replaceExisting=...)`
- After import, `.restore_queued` markers queue `apply_work` on next student hello (`delivery.queueWorkRestore`).

## Delete classroom

Confirm warns if `delivery.workCacheHasBundles` is true. Export first if you need a backup.

## Files

| File | Role |
|------|------|
| `workpack.py` | parts registry, lesson tar helpers |
| `archive.py` | timestamped export/import |
| `delivery.py` | collect flags |
| `publisher.py` | collect / report / apply_work |
| `agent.py` | pack report, unpack work and lessons |
