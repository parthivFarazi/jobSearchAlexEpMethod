---
description: Score a job URL against Parthiv's spec, build the package in the main workspace, prefill the form in Chrome, never submit
---
The user gives a job-posting URL or a pasted JD as: $ARGUMENTS

This command is the kit's /apply, rewired to the system that already exists. Nothing here replaces the
main workspace's rules. WORKSPACE = `/Users/parthiv_farazi/Documents/job-search/Job Search Figured Out`.

0. **Load the rules first.** Read `WORKSPACE/CLAUDE.md`, then the START HERE block of `WORKSPACE/00_OPS/now-state.md`,
   then `WORKSPACE/00_OPS/parthiv-job-search-spec.md` sections 2, 3, 3a, 6, 7, and the
   "CONSOLIDATED RULE, WORK AUTHORISATION SCREENING" in `WORKSPACE/00_OPS/preferences-and-decisions-log.md`.
   The six writing rules apply to every word he signs. No em-dashes, no en-dashes, no semicolons, no colons
   in prose, audit-checked numbers only, Pong is an anchor not a law.

1. **Get the live target.** Fetch the posting (Greenhouse: `boards-api.greenhouse.io/v1/boards/<token>/jobs/<id>?questions=true`,
   Ashby: `api.ashbyhq.com/posting-api/job-board/<token>`, otherwise WebFetch, fallback `curl -sL`). Extract company,
   exact title, location and workplace model, start date, required and preferred qualifications, compensation,
   short-answer questions, and every work-authorisation sentence. Quote the body, never the URL slug.

2. **Hard filters before anything else** (spec section 2). Senior, Staff, Principal, Lead in the title, or 3+ years in
   the body, stops here. Work authorisation: `citizen`, `permanent resident`, `student visa`, `ITAR`, `export`,
   `clearance` at rank 1 or 2 is dead. "Unable to sponsor" is high risk, report it and ask before investing.
   A neutral form is fine and is not penalised. Posting age is a modifier on Interview probability, never a filter.
   A June 2027 or later start is usually fatal under the OPT 90-day cap. Say so plainly if you see it.

3. **Dedup and leads.** `grep -ril` the company in `WORKSPACE/application/` and the URL in every
   `06_application_spec.json`. If a package exists, stop and report its status. Then grep the real company name in
   `WORKSPACE/03_OUTREACH/du_alumni/alumni_by_company.md`. A DU brother is a lead to surface in `07_outreach/messages.md`,
   not a score boost until Parthiv confirms he can ask.

4. **Score /60** on the six axes with the 3a age modifier and boosts. Below 45, report the score and the reasons and
   stop, unless he says build anyway (the passion-role exception exists and is his call).

5. **Build the package** at `WORKSPACE/application/YYYY-MM-DD_Company_Role/` exactly as spec section 7 lists it.
   Resume selection follows `WORKSPACE/00_OPS/resume_lab/README.md`, score coverage of the JD's demands and write
   `_meta.selection` into `04_resume.json`. Render with
   `python3 WORKSPACE/00_OPS/resume_template/render_resume.py 04_resume.json 04_resume.pdf` and it must exit clean on one page.
   Letter only if the form takes one, rendered with `render_cover_letter.py`. Draft every short-answer question in his
   voice in `06_application_answers.md`. `06_application_spec.json` carries a live-verified `application_url` and
   `status: ready_to_apply`. Start `99_log.md` with the posted date and the score.

6. **Open the application in Chrome** (Claude in Chrome) and prefill text and select fields from the spec file.
   Stop at the resume upload, every self-identification question, and Submit. He does those three himself, always.
   Show every answer you typed so he can check the work-authorisation and sponsorship fields.

7. **Receipts.** The session that is in the browser when he submits writes the receipt at that moment, a dated entry in
   `99_log.md` with the confirmation id, `status: applied` and `submitted_at` in `06_application_spec.json`, and one line at
   the top of the Activity log in `WORKSPACE/00_OPS/now-state.md`. Never ask him for a "sent" message later.

8. **Update now-state.** Dated entry at the top of the Activity log. The `**Last updated:**` line stays one line, the date
   plus one sentence. Do not prepend a summary to it.
