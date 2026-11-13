# alexEpMethod, the hourly job watcher

This folder is the full-time edition of the "Build Your Own Internship Watcher" starter kit, built 2026-11-13.
Read `README.md` first. It explains every filter and what Parthiv still has to do himself (GitHub repo, secrets).

The job-search brain lives one folder over at `../Job Search Figured Out/`. Its `CLAUDE.md`, `00_OPS/now-state.md`
and `00_OPS/parthiv-job-search-spec.md` are the source of truth for every rule `config.json` encodes. Change a rule
there first, then mirror it here, then run `DRY_RUN=1 python3 watcher.py` and read the Filter drops line.

Rules that carry over whole:
- Posting age is a modifier, never a filter. Ashby `publishedAt` is an original date, not freshness.
- Work authorisation. Citizenship, LPR, ITAR, clearance, "student visa" kills. "Unable to sponsor" only flags.
- Silent drops are the most dangerous bug. Every drop is logged with a reason. Keep it that way.
- Word-boundary matching only. `intern` must never match Internal or International.
- He does the resume upload, self-identification and Submit himself. The `/apply` command stops there.
- The six writing rules apply to anything he signs. Emails from the watcher go only to him, but keep the style anyway.
