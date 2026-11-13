# Job Watcher, full-time edition

An hourly watcher for entry-level software, ML and data roles, built on 2026-11-13 from the "Build Your Own
Internship Watcher" starter kit (the PDF in Downloads). One Python file polls 117 company boards (Greenhouse,
Lever, Ashby, Workable, Workday) plus the SimplifyJobs and vanshb03 new-grad tracker repos, keeps the roles
Parthiv can actually take, logs every drop with a reason, and emails only what is new since the last run.
It runs on GitHub's free Actions cron with the laptop off. State lives in the repo.

The job-search brain is one folder over at `../Job Search Figured Out/`. Every filter in `config.json` encodes a
rule written down there. The watcher finds. The brain scores and builds. Nothing here submits anything.

## What changed from the internship kit, and the rule each change comes from

| Internship kit | Full-time edition | Where the rule lives |
|---|---|---|
| Title must contain `intern` | `intern`, `co-op` and `coop` are excluded. Title must contain a domain word (software, engineer, ML, data, forward deployed, solutions, founding, and so on) | Spec section 4 archetypes |
| Cycle-year check on the title and body | Years-of-experience check on the body. A stated floor above 2 years drops the role. No floor stated keeps it, exactly like the kit keeps a title with no year. New grad, early career and 0-2 wording overrides a stray number | Spec section 2, YOE row |
| No work-authorisation logic | Citizenship, permanent resident, green card holder, clearance, ITAR, export control, polygraph and "student visa" language drops with a logged reason. "Unable to sponsor" only flags. OPT, CPT, E-Verify and "we sponsor" flag positively. A negation guard keeps "does not require US citizenship" alive | Decisions log, CONSOLIDATED RULE, ranks 1, 2, 3, 4, 6 |
| No seniority words | Senior, Sr, Staff, Principal, Lead, Director, Manager, Architect, III and IV in the title drop | Spec section 2, title bar |
| Every passing role is kept | Big-board rule. A board with 60 or more live jobs lists every level, so a role there needs an entry-level signal (title words, body words, or a stated floor of 2 years or less). Boards under 60 jobs keep every passing role, which is the Sim and Mechanize case. Trackers are entry level by construction | Spec section 12, implicit senior bars at tier-1 boards |
| No age handling | Age is shown with the modifier (+2 for 24 hours down to -2 past 90 days) and never filtered. Greenhouse uses `updated_at`. Ashby dates are labelled as original publish dates | Spec section 3a and its four exceptions |
| No start-date handling | June 2027 or later start flags LATE START. January to April 2027 flags early start | Now-state hard constraint 1, the OPT 90-day cap from 2027-02-08 |
| Quant firms in the default list | All quant and prop trading excluded, with Appian, American Express, Cargill, Falcomm and PrizePicks (struck in now-state), and the defense and federal-lab class (SpaceX, Anduril, the primes, APL, MITRE) which is US-person by definition | Now-state struck list, decisions log GTRI corollary |
| Exclude a few countries | US first, then UK, Ireland, Canada, Australia and Singapore tagged non-US. Everything else is excluded. Keep markers rescue multi-location strings that mention a US city | Spec section 11. Europe for an exceptional fit stays a manual call |
| One tracker repo | SimplifyJobs New-Grad-Positions (the highest-yield aggregator in the decisions log) and vanshb03. Structured fields are used. Citizenship-required rows drop, no-sponsor rows flag, Hardware, Quant and Product categories drop, rows whose degree list has no Bachelor's drop | Decisions log, 2026-10 SimplifyJobs note |
| No Workday | `fetch_workday` for NVIDIA and Salesforce, with a search term that narrows the list to new grad | Kit section 7 upgrade, applied because several of his targets live on Workday |
| URL string dedupe | Canonical job ids across URL forms (Greenhouse embed vs board, Ashby, Lever, Workday, Workable). A tracker row that repeats a company and title already kept folds into that line with its location merged, and is marked seen | New |
| Empty seen list | Seeded with the 187 roles already packaged in the main workspace, so the baseline never re-surfaces something he has already applied to | New |
| Email only | `latest_new.md` is written and committed every run, so a brain session can read the finds without the inbox | New |

## Files

- `watcher.py`, the whole thing, about 470 lines. Fetchers, filters, tags, dedupe, email, `probe` and `seed` subcommands.
- `config.json`, filters and the board list. The only file you normally edit.
- `seen_jobs.json`, state. Committed back by the workflow after every run. Delete it for a fresh baseline (re-seed first, see below).
- `latest_new.md`, what the last run found, committed every run.
- `.github/workflows/watch.yml`, hourly cron at :17 plus a Run workflow button.
- `.claude/commands/apply.md`, the `/apply <url>` command for Claude Code, rewired to the main workspace's package rules.
- `preview.html` and `preview.md`, dry-run output, ignored by git.

## What Parthiv does himself (about 15 minutes, once)

The code is done and dry-run tested. These three steps need his accounts, so they are his.

1. **GitHub repo.** Create a new repository on github.com (public is fine, there are no secrets in the code), for example
   `job-watcher`. Do not add a README or .gitignore there. Then, in this folder, which is already a git repo with the
   first commit made:

   ```bash
   cd /Users/parthiv_farazi/Documents/job-search/alexEpMethod
   ```
   ```bash
   git remote add origin https://github.com/parthivFarazi/job-watcher.git
   ```
   ```bash
   git push -u origin main
   ```
   (Swap the URL for the repo you created. `gh` is not installed on this machine, so the UI is the way.)

2. **Gmail App Password.** Google Account, Security, 2-Step Verification on, App passwords, create one named `watcher`.
   Copy the 16-character code. It is not the normal password.

3. **Repo secrets.** Repo, Settings, Secrets and variables, Actions, New repository secret, three times.
   `SMTP_USERNAME` is the Gmail address the alerts send from. `SMTP_PASSWORD` is the app password.
   `EMAIL_TO` is where alerts land, comma-separated if several (`parthivfarazi@icloud.com,pfarazi3@gatech.edu`).

Then Actions, Job Watcher, Run workflow. The first run emails a baseline of everything currently open that passes
the filters and was updated in the last 30 days (older roles are in `latest_new.md`, never dropped). Every later
email contains only what opened since the previous hour. Read the run log once. Every board prints `ok` or `x ... skipped`.

## Running it locally

```bash
cd /Users/parthiv_farazi/Documents/job-search/alexEpMethod && DRY_RUN=1 python3 watcher.py
```
Prints what it found, writes `preview.html` and `preview.md`, sends nothing, saves no state. Takes about 30 seconds.

```bash
cd /Users/parthiv_farazi/Documents/job-search/alexEpMethod && python3 watcher.py probe "Ramp" "Hudson River Trading" figma
```
Guesses the board token for each company name and prints a ready-to-paste config entry.

```bash
cd /Users/parthiv_farazi/Documents/job-search/alexEpMethod && python3 watcher.py seed "/Users/parthiv_farazi/Documents/job-search/Job Search Figured Out/application"
```
Marks every `application_url` in the main workspace's package folders as seen. Run it again after a sweep builds
new packages, and before deleting `seen_jobs.json` for a fresh baseline.

## Adding a company

The token is the slug in the careers URL. `job-boards.greenhouse.io/stripe` is `{"name": "Stripe", "ats": "greenhouse", "token": "stripe"}`.
`jobs.ashbyhq.com/ramp` is Ashby, `jobs.lever.co/palantir` is Lever, `apply.workable.com/pony-dot-ai` is Workable.
Workday needs host, tenant and site, read from the careers URL (`nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`),
and a `search` term so the list is not the whole company. Google, Meta, Apple, Microsoft and Amazon careers pages are
JavaScript apps that cannot be polled. Set native alerts there and rely on the trackers.

Per-firm `"mode": "all"` forces every passing role through, `"mode": "entry"` forces the entry-signal requirement.
`"enabled": false` parks a board. Five boards from old sourcing docs are parked that way because they 404 now.

## Tuning filters without silently breaking things

After any change run the dry run and read the `Filter drops` line. If a reason you did not expect is dropping hundreds,
the filter is wrong. The drop reasons are `no-domain-match`, `excluded:<word>`, `excluded-company`, `wrong-year-in-title`,
`wrong-cycle-phrase`, `citizenship-required(tracker)`, `tracker-category:<cat>`, `degree-no-bachelors`, `work-auth:<why>`,
`senior-plus-in-body`, `too-senior-yoe:<n>+`, `no-entry-signal(big-board)` and `excluded-location`.

Matching is word-boundary on purpose. `intern` never matches Internal or International, `data` never matches database,
`engineer` does match engineering. Spaces in a term match a space or a hyphen. Keep it that way for any gate you add.

Never require the year in the title. Never filter on age. Both lessons cost the kit's author weeks and this workspace months
(NCR Voyix was invisible for a season because a sweep filtered on recency).

## Routing a hit into the main workspace

Nothing in the email is scored. A promising line goes through the normal process. Open a Claude Code session in this folder
and type `/apply <url>`, or in the main workspace follow spec section 7. The hard filters run again on the live JD, the
DU alumni directory is grepped, the role is scored out of 60, and a package is built only at 45 or above unless Parthiv
says otherwise. He uploads the resume, answers self-identification and clicks Submit himself, always.

## Gotchas carried over from the kit, plus new ones

1. Never require the year in the title. 2. Silent drops are the most dangerous bug, so every drop is logged.
3. Keep polling parallel (12 threads). 4. Word boundaries only. 5. Trackers lag, boards do not, so poll the board when you can.
6. Trackers go stale. The two configured ones were live on 2026-11-13. 7. GitHub throttles top-of-hour cron, the schedule is :17.
8. The workflow rebases before pushing. 9. JavaScript careers pages cannot be polled.
10. Ashby `publishedAt` is an original date. Deposco and Vals AI had live reqs published a year earlier. Old on Ashby means standing need.
11. A tracker row has no body, so the YOE and work-auth checks cannot run on it. The email says "no body, screen manually".
12. Workday bodies are fetched only for the first 40 title-relevant jobs per board, to keep the run short.
13. Gmail clips mail over 102 KB, so the baseline email lists the 30-day set and counts the rest.
