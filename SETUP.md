# Go-live checklist, about 15 minutes

Everything below needs your accounts, which is why it was left for you. The code is done, dry-run tested and committed.

## 1. Create the GitHub repo (2 minutes)

1. Open https://github.com/new while signed in as parthivFarazi.
2. Repository name: `job-watcher`
3. Visibility: Public (there are no secrets in the code, they live in GitHub's secret store).
4. Leave "Add a README file" UNCHECKED. Leave .gitignore as None. Leave License as None. The repo must be empty.
5. Click "Create repository". Leave the page open, you will refresh it in step 2.

## 2. Push the watcher (1 minute)

Open Terminal (or the Terminal tab in the Claude app) and run these three commands one at a time.

    cd /Users/parthiv_farazi/Documents/job-search/alexEpMethod

    git remote add origin https://github.com/parthivFarazi/job-watcher.git

    git push -u origin main

Your GitHub login is already cached on this Mac, so no prompt is expected. If a password prompt does appear, GitHub does not accept your account password there. Create a token at https://github.com/settings/tokens, "Generate new token (classic)", tick `repo` and `workflow`, and paste the token as the password.

Check: refresh the repo page. You should see watcher.py, config.json, seen_jobs.json, README.md and "3 commits".

## 3. Let the workflow write back to the repo (30 seconds)

The watcher commits its own state after each run.

1. Repo page, "Settings" tab, left sidebar "Actions", then "General".
2. Scroll to "Workflow permissions". Select "Read and write permissions". Click Save.

## 4. Gmail App Password (3 minutes)

Use a gmail.com account, for example pfarazi3.gatech.edu@gmail.com. The gatech.edu Workspace account may block app passwords.

1. Open https://myaccount.google.com/security signed in to that Gmail.
2. "2-Step Verification" must be On. If it is Off, turn it on first (phone prompt or SMS), then come back.
3. Open https://myaccount.google.com/apppasswords
4. App name: `watcher`. Click Create.
5. A 16-character code appears, shown as four groups of four. Copy it. Remove the spaces when you paste it in step 5. This is the only time Google shows it. If you lose it, delete it and create another.

## 5. Add the three secrets (2 minutes)

1. Repo page, "Settings" tab, left sidebar "Secrets and variables", then "Actions".
2. Click "New repository secret" three times, one secret each. Names must match exactly, all caps.

| Name | Value |
|---|---|
| `SMTP_USERNAME` | the Gmail address you made the app password in, e.g. pfarazi3.gatech.edu@gmail.com |
| `SMTP_PASSWORD` | the 16-character app password, no spaces |
| `EMAIL_TO` | where alerts land, e.g. parthivfarazi@icloud.com (several addresses: separate with commas, no spaces) |

## 6. Run it once (2 minutes)

1. Repo page, "Actions" tab. If GitHub asks you to enable workflows, click the green button.
2. Left sidebar, click "Job Watcher".
3. Right side, "Run workflow" dropdown, then the green "Run workflow" button.
4. Wait about a minute, refresh, click the run that appears, click the "watch" job, expand "Run watcher".

What a good log looks like. One line per board, `ok Harvey: 377 jobs, 11 relevant` or `x SomeBoard skipped: 404`. Then one `Filter drops:` line. Then `Email sent to ['...']: [Job Watcher] Baseline: ~1990 open role(s)`. Then `Tracked 2052 relevant live roles ...`.

5. Check the inbox you put in EMAIL_TO. Subject starts with `[Job Watcher] Baseline:`. It lists the roles from the last 7 days, about 250, and counts the older ones.
6. Refresh the repo page. A new commit "Update seen jobs [skip ci]" by github-actions[bot] and a new file `latest_new.md` mean the state saved.

From here the cron runs every hour at :17 and emails only what is new. Nothing to maintain.

## If something fails

- Log says `set SMTP_USERNAME, SMTP_PASSWORD (Gmail App Password), EMAIL_TO`. A secret name is misspelled or missing. Fix in step 5, rerun step 6.
- Log shows `! SMTP attempt 1: (535 ...)` three times. The app password is wrong, has spaces, or 2-Step Verification is off. Redo step 4, update SMTP_PASSWORD, rerun.
- The "Save state" step is red. Step 3 was skipped. Fix it, rerun.
- No email but the log says `No new roles this run.` Normal on a quiet hour.
- A board prints `x ... skipped: 404`. That board changed or closed. Park it in config.json with `"enabled": false`, or re-probe: `python3 watcher.py probe "Company Name"`.
- An hour is skipped. GitHub throttles scheduled runs on quiet repos. It catches up next hour.

## After every sweep that builds packages

So the watcher stops surfacing roles you already have. Three commands, from the watcher folder.

    python3 watcher.py seed "/Users/parthiv_farazi/Documents/job-search/Job Search Figured Out/application"

    git add seen_jobs.json && git commit -m "Re-seed from workspace"

    git pull --rebase && git push

## Acting on an alert

Nothing in the email is scored. Open a Claude Code session in the watcher folder and type `/apply <job url>`, or hand the URL to a session in the main workspace. The hard filters run again on the live JD, the DU directory is grepped, the role is scored out of 60, and a package is built at 45 or above. You upload the resume, answer self-identification and click Submit yourself.
