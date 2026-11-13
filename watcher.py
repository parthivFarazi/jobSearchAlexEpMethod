#!/usr/bin/env python3
"""
Job Watcher -- full-time edition of the "Build Your Own Internship Watcher" starter kit.

Polls company job boards (Greenhouse / Lever / Ashby / Workable / Workday) plus the
SimplifyJobs and vanshb03 new-grad tracker repos every hour on GitHub Actions, keeps the
entry-level software / ML / data roles Parthiv can actually take, drops what the master
spec says to auto-skip (and LOGS every drop), and emails only what is NEW since last run.

Run:    SMTP_USERNAME=... SMTP_PASSWORD=... EMAIL_TO=... python watcher.py
Dry:    DRY_RUN=1 python watcher.py           (prints, writes preview.html + preview.md, saves no state)
Probe:  python watcher.py probe "Ramp" figma   (guess board tokens for company names)
Seed:   python watcher.py seed "/path/to/Job Search Figured Out/application"
        (marks every URL already packaged in the main workspace as seen, so the first
         baseline email does not re-surface roles he has already applied to)
"""
import json, os, re, sys, time, smtplib, html as htmlmod
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
import requests

CONFIG_FILE, SEEN_FILE, LATEST_MD, TIMEOUT = "config.json", "seen_jobs.json", "latest_new.md", 25
DRY_RUN = os.environ.get("DRY_RUN") == "1"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"}
NOW = time.time()
FILTERS = {}            # set in main(); fetch_workday needs the title gate before it fetches bodies


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, json.JSONDecodeError): return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)

def _plain(s):
    """HTML (or HTML-escaped HTML, which Greenhouse returns) -> lowercase plain text."""
    s = htmlmod.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).lower()

def _epoch(v):
    """ISO string / unix seconds / unix milliseconds / YYYY-MM-DD -> unix seconds, or None."""
    if v in (None, ""): return None
    if isinstance(v, (int, float)): return v / 1000 if v > 1e11 else float(v)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError: return None

def _workday_days(text):
    t = (text or "").lower()
    if "today" in t: return 0
    if "yesterday" in t: return 1
    m = re.search(r"(\d+)\+?\s*days?", t)
    return int(m.group(1)) + (1 if "+" in t else 0) if m else None

# ------------------------------ board fetchers ------------------------------ #
# Each returns normalized dicts: {id, title, location, url, content, posted_at, company?, ...}.
# content is lowercase plain text. posted_at is unix seconds or None.

def fetch_greenhouse(firm):
    r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{firm['token']}/jobs?content=true", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [{"id": str(j.get("id")), "title": j.get("title") or "", "location": (j.get("location") or {}).get("name") or "",
             "url": j.get("absolute_url") or "", "content": _plain(j.get("content")),
             "posted_at": _epoch(j.get("updated_at") or j.get("first_published"))}   # spec 3a: use updated_at on Greenhouse
            for j in r.json().get("jobs", [])]

def fetch_lever(firm):
    r = requests.get(f"https://api.lever.co/v0/postings/{firm['token']}?mode=json", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [{"id": str(j.get("id")), "title": j.get("text") or "", "location": (j.get("categories") or {}).get("location") or "",
             "url": j.get("hostedUrl") or "", "content": _plain(j.get("descriptionPlain")), "posted_at": _epoch(j.get("createdAt"))}
            for j in r.json()]

def fetch_ashby(firm):
    r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{firm['token']}?includeCompensation=false", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for j in r.json().get("jobs", []):
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in (j.get("secondaryLocations") or [])]
        out.append({"id": str(j.get("id")), "title": j.get("title") or "", "location": ", ".join(x for x in locs if x),
                    "url": j.get("jobUrl") or j.get("applyUrl") or "", "content": _plain(j.get("descriptionPlain")),
                    "posted_at": _epoch(j.get("publishedAt")), "date_is_original": True})   # spec 3a: Ashby publishedAt is NOT freshness
    return out

def fetch_workable(firm):
    r = requests.get(f"https://apply.workable.com/api/v1/widget/accounts/{firm['token']}?details=true", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return [{"id": str(j.get("shortcode") or j.get("id")), "title": j.get("title") or "",
             "location": ", ".join(x for x in [j.get("city"), j.get("state"), j.get("country")] if x),
             "url": j.get("url") or j.get("application_url") or "", "content": _plain(j.get("description")),
             "posted_at": _epoch(j.get("published_on") or j.get("created_at"))} for j in r.json().get("jobs", [])]

def fetch_workday(firm):
    """Workday CXS. config: host, tenant, site, optional search (narrows the list) and max_pages.
    The list endpoint has no body, so bodies are fetched only for title-relevant jobs (cap 40)."""
    host, tenant, site = firm["host"], firm["tenant"], firm["site"]
    base, hdr = f"https://{host}/wday/cxs/{tenant}/{site}", {**HEADERS, "Content-Type": "application/json"}
    out, offset, limit = [], 0, 20
    for _ in range(int(firm.get("max_pages", 10))):
        r = requests.post(f"{base}/jobs", json={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": firm.get("search", "")}, headers=hdr, timeout=TIMEOUT)
        r.raise_for_status()
        posts = r.json().get("jobPostings", [])
        for p in posts:
            path = p.get("externalPath") or ""
            days = _workday_days(p.get("postedOn"))
            out.append({"id": path.rsplit("_", 1)[-1] or path, "title": p.get("title") or "", "location": p.get("locationsText") or "",
                        "url": f"https://{host}/{site}{path}", "content": "", "posted_at": (NOW - days * 86400) if days is not None else None,
                        "_detail": f"{base}{path}"})
        if len(posts) < limit: break
        offset += limit
    for j in [j for j in out if _title_passes(j["title"], FILTERS)][:40]:
        try:
            info = requests.get(j["_detail"], headers=HEADERS, timeout=TIMEOUT).json().get("jobPostingInfo", {})
            j["content"] = _plain(info.get("jobDescription"))
            j["posted_at"] = _epoch(info.get("startDate")) or j["posted_at"]
        except Exception: pass
    return out

def fetch_github_json(firm):
    """Community tracker repos that publish listings.json (SimplifyJobs / vanshb03 family).
    One source = hundreds of companies. Structured fields (sponsorship, category, degrees) are carried
    through so the filters can use them. Trackers lag boards, so the same job usually also arrives
    from the company board; canon_key() and the company|title|location key dedupe the pair."""
    r = requests.get(firm["url"], headers=HEADERS, timeout=60); r.raise_for_status()
    out = []
    for j in r.json():
        if not isinstance(j, dict) or j.get("active") is False or j.get("is_visible") is False: continue
        locs = j.get("locations") or j.get("location") or []
        title = (j.get("title") or "").strip()
        out.append({"id": str(j.get("id") or j.get("url") or title), "title": title,
                    "company": (j.get("company_name") or j.get("company") or "").strip(),
                    "location": ", ".join(map(str, locs)) if isinstance(locs, list) else str(locs),
                    "url": j.get("url") or j.get("application_link") or "", "content": "",
                    "posted_at": _epoch(j.get("date_updated") or j.get("date_posted")),
                    "sponsorship": j.get("sponsorship") or "", "category": j.get("category") or "",
                    "degrees": j.get("degrees") or [], "tracker": firm["name"]})
    return out

FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
            "workable": fetch_workable, "workday": fetch_workday, "github_json": fetch_github_json}

# --------------------------------- filters ---------------------------------- #
DROPS = {}
def _drop(reason, title):
    DROPS.setdefault(reason, []).append(title); return False

def _word_re(term):
    """Word-boundary pattern. 'intern' matches intern/interns/internship, never Internal/International.
    'engineer' matches engineers/engineering. Spaces in a term match space or hyphen (full stack / full-stack)."""
    t = re.escape(term.lower()).replace(r"\ ", r"[\s-]+")
    suffix = "" if len(term) <= 3 else r"(?:s|es|ing|ship|ships|er|ers)?"
    return rf"(?<![a-z0-9]){t}{suffix}(?![a-z0-9])"

def _has_term(text, term): return re.search(_word_re(term), text) is not None

def _norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())

def company_excluded(company, f):
    c = _norm(company)
    return any(c == _norm(x) or (len(_norm(x)) >= 4 and c.startswith(_norm(x))) for x in f.get("company_exclude", []))

def _title_passes(title, f):
    """Title-level gates only (domain + exclude). Workday uses this before spending a body fetch."""
    t = title.lower()
    if f.get("title_require_any") and not any(_has_term(t, k) for k in f["title_require_any"]): return False
    return not any(_has_term(t, b) for b in f.get("title_exclude", []))

NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
def _n(x): return NUMWORDS.get(x, None) if not x.isdigit() else int(x)
YOE_PATTERNS = [   # each yields the MINIMUM years the sentence asks for
    r"(?<![a-z0-9])(\d{1,2})\s*\+?\s*(?:-|–|to)\s*\d{1,2}\s*\+?\s*(?:years?|yrs?)(?:'|’)?[^.;]{0,90}?(?:experience|exp(?![a-z]))",     # 2-12+ years of ... experience
    r"(?<![a-z0-9])(\d{1,2})\s*\+\s*(?:years?|yrs?)(?:'|’)?(?:\s+(?:of|in|working|building|as|with|leading|shipping)(?![a-z])|[^.;]{0,90}?(?:experience|exp(?![a-z])))",   # 5+ years of / in ...
    r"(?<![a-z0-9])(\d{1,2})\s*(?:years?|yrs?)\s*\+\s*(?:of\s+)?[^.;]{0,60}?(?:experience|exp(?![a-z]))",     # 4 years + experience
    r"(?:minimum|at least|min\.?)\s+(?:of\s+)?(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\+?\s*(?:years?|yrs?)",
    r"(?<![a-z0-9])(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\+?\s*(?:or more\s+)?(?:years?|yrs?)(?:'|’)?,?\s+(?:of\s+)?(?:[\w'-]+\s+){0,5}?(?:experience|exp(?![a-z]))",   # 3 years of full-time experience
]
ENTRY_LEVEL_RE = r"(?<![a-z0-9])(new ?grads?|new graduates?|recent graduates?|entry[- ]level|early[- ]career|early[- ]in[- ]career|university grad(uate)?s?|campus hires?|graduating (students|seniors)|class of 202[67]|0\s*(-|–|to)\s*[123]\s*(years?|yrs?)|no (prior |previous )?(work |industry |professional )?experience (is )?(required|necessary|needed))(?![a-z0-9])"
NEGATION_RE = r"(not|no|never|without|regardless of|irrespective of|does not|do not|don't|doesn't)\s+(\w+\s+){0,3}$"
AUTH_KILL = [   # ranks 1 and 2 of the work-authorisation hierarchy: no path for F-1
    (r"(u\.?s\.?|united states) citizen", "us-citizen"), (r"citizenship (is )?(required|mandatory|needed)", "citizenship-required"),
    (r"must be (a |an )?(u\.?s\.? )?citizen", "must-be-citizen"), (r"(?<![a-z])permanent residents?(?![a-z])", "permanent-resident"),
    (r"green card holders?", "green-card-holder"), (r"security clearance", "clearance"), (r"clearance (is )?required", "clearance"),
    (r"(?<![a-z])(ts/sci|top secret)(?![a-z])", "clearance"), (r"(?<![a-z])itar(?![a-z])", "itar"), (r"export control", "export-control"),
    (r"(?<![a-z])polygraph(?![a-z])", "polygraph"), (r"student visa", "student-visa-excluded"),
]
NO_SPONSOR_RE = (r"((unable|not able|cannot|can ?not|can't|do(es)? not|will not|won't|not currently|not in a position|aren't able|are not able) (to )?"
                 r"(currently |presently |now )?(provide |offer |consider |support )?(employment |work |visa |immigration |h-?1b )?(visa )?sponsor"
                 r"|no (visa |immigration |employment |h-?1b )?sponsorship|sponsorship (is )?(not |un)available|not eligible for (visa )?sponsorship"
                 r"|without (the need for |requiring |need of )?(current or future |now or in the future |present or future )?(visa |employment |work |immigration )?(authorization )?sponsorship)")
SPONSOR_OK_RE = (r"((?<![a-z])opt(?![a-z-])|(?<![a-z])cpt(?![a-z])|(?<![a-z])e-?verify(?![a-z])|we (do |will |can |are happy to |are able to )?(sponsor|provide sponsorship|offer sponsorship)"
                 r"|(visa|h-?1b|immigration|work) sponsorship (is )?(available|offered|provided|possible)|sponsorship (is )?available|open to (candidates )?(with|on) (opt|cpt)"
                 r"|(will|happy to|able to|willing to) sponsor)")
START_LATE_RE = r"((start|begin|join)\w*[^.;]{0,50}(?<![a-z])(summer|june|july|august|fall|september|october|november|december) (of )?2027|(summer|june|july|august|fall|september) 2027 start)"
START_EARLY_RE = r"((start|begin|join)\w*[^.;]{0,50}(?<![a-z])(january|jan|february|feb|march|april|winter|spring|q1) (of )?2027|(january|february|winter|spring) 2027 start)"

def yoe_minimums(content):
    mins = []
    for pat in YOE_PATTERNS:
        for m in re.finditer(pat, content):
            n = _n(m.group(1))
            if n is not None and n <= 30: mins.append(n)
    return mins

def _negated(content, pos):
    return re.search(NEGATION_RE, content[max(0, pos - 70):pos]) is not None

def entry_signal(job, f):
    """True when the posting says it is entry level: title words, body words, or a stated YOE floor within the bar."""
    title, content = job["title"].lower(), job.get("content") or ""
    if re.search(ENTRY_LEVEL_RE, title) or any(_has_term(title, w) for w in ("junior", "associate", "graduate")) \
            or re.search(r"(?<![a-z0-9])(i|1|2026|2027)(?![a-z0-9])", title): return True
    if content and re.search(ENTRY_LEVEL_RE, content): return True
    mins = yoe_minimums(content)
    return bool(mins) and min(mins) <= int(f.get("max_years_required", 2))

def is_relevant(job, f):
    title, content = job["title"].lower(), job.get("content") or ""
    if company_excluded(job.get("company", ""), f): return _drop("excluded-company", f"{job.get('company')}: {title}")
    if f.get("title_require_any") and not any(_has_term(title, k) for k in f["title_require_any"]): return _drop("no-domain-match", title)
    for bad in f.get("title_exclude", []):
        if _has_term(title, bad): return _drop(f"excluded:{bad}", title)
    # CYCLE CHECK, same shape as the internship kit. NEVER require the year in the title; most companies omit it.
    years = [str(y) for y in f.get("years", [])]
    ty = set(re.findall(r"(?<![a-z0-9])(20\d{2})(?![a-z0-9])", title))
    if years and ty and not (ty & set(years)): return _drop("wrong-year-in-title", title)
    if years and not ty and content:
        if not any(y in content for y in years) and any(p.lower() in content for p in f.get("reject_cycle_phrases", [])):
            return _drop("wrong-cycle-phrase", title)
    # Tracker structured fields (SimplifyJobs / vanshb03).
    if job.get("tracker"):
        if "citizenship" in (job.get("sponsorship") or "").lower(): return _drop("citizenship-required(tracker)", title)
        keep = [c.lower() for c in f.get("tracker_category_keep", [])]
        if keep and job.get("category") and job["category"].lower() not in keep: return _drop(f"tracker-category:{job['category']}", title)
        degs = [str(d).lower() for d in (job.get("degrees") or [])]
        if degs and not any(d.startswith(("bachelor", "associate")) for d in degs): return _drop("degree-no-bachelors", title)
    # Body checks. A missing body (tracker rows, Workday beyond the cap) is KEPT, like the kit keeps a title with no year.
    if content:
        for pat, why in AUTH_KILL:
            m = re.search(pat, content)
            if m and not _negated(content, m.start()): return _drop(f"work-auth:{why}", title)
        if re.search(r"(senior|staff)\s?\+", content): return _drop("senior-plus-in-body", title)
        mins = yoe_minimums(content)
        if mins and min(mins) > int(f.get("max_years_required", 2)) and not re.search(ENTRY_LEVEL_RE, f"{title} {content}"):
            return _drop(f"too-senior-yoe:{min(mins)}+", title)
    # Big company boards list every level. An unlabelled "Software Engineer" there is almost never entry level
    # (spec 12: tier-1 boards carry implicit senior bars). Small boards keep every passing role, the Sim / Mechanize case.
    if job.get("_mode") == "entry" and not entry_signal(job, f): return _drop("no-entry-signal(big-board)", title)
    loc = (job.get("location") or "").lower()
    if loc and f.get("location_exclude") and any(_has_term(loc, b) for b in f["location_exclude"]):
        if not any(m.lower() in loc for m in f.get("location_keep_markers", [])): return _drop("excluded-location", f"{title} @ {loc}")
    return True

# ------------------------------ annotations --------------------------------- #
def age_days(job):
    return None if not job.get("posted_at") else max(0.0, (NOW - job["posted_at"]) / 86400)

def age_label(job):
    """Spec 3a. A modifier on Interview probability, never a filter. Ashby dates are original publish dates."""
    d = age_days(job)
    if d is None: return "age ?"
    mod = "+2" if d <= 1 else "+1" if d <= 7 else "0" if d <= 30 else "-1" if d <= 90 else "-2"
    txt = "today" if d < 1 else f"{int(d)}d"
    if job.get("date_is_original"): return f"published {datetime.fromtimestamp(job['posted_at'], timezone.utc):%Y-%m-%d} (Ashby original date, not freshness)"
    return f"{txt} ({mod})"

def tags(job, f):
    t, title, content, loc = [], job["title"].lower(), job.get("content") or "", (job.get("location") or "").lower()
    if re.search(ENTRY_LEVEL_RE, title) or _has_term(title, "junior") or _has_term(title, "associate") or re.search(r"(?<![a-z0-9])(i|1)(?![a-z0-9])", title): t.append("entry-level title")
    sp = (job.get("sponsorship") or "").lower()
    if "offers sponsorship" in sp: t.append("sponsor (tracker)")
    if "does not offer" in sp: t.append("NO-SPONSOR language (tracker)")
    if content:
        if re.search(SPONSOR_OK_RE, content): t.append("OPT/sponsor language")
        if re.search(NO_SPONSOR_RE, content): t.append("NO-SPONSOR language, ask before investing")
        if re.search(START_LATE_RE, content): t.append("LATE START mid-2027, check OPT cap")
        elif re.search(START_EARLY_RE, content): t.append("early-2027 start")
        mins = yoe_minimums(content)
        if mins: t.append("yoe " + "/".join(f"{n}+" for n in sorted(set(mins))[:3]))
    else: t.append("no body, screen manually")
    if loc and any(_has_term(loc, m) for m in f.get("international_markers", [])) and not any(m.lower() in loc for m in f.get("location_keep_markers", [])): t.append("non-US")
    if job.get("tracker"): t.append(f"via {job['tracker']}")
    return t

# --------------------------------- dedupe ----------------------------------- #
def canon_key(url, company="", jid=""):
    """One key per job however it was reached: greenhouse embed vs board URL, Simplify link vs direct, etc."""
    u = (url or "").strip().lower()
    for pat, pre in ((r"greenhouse\.io/(?:embed/job_app\?(?:[^#]*&)?token=|[^/]+/jobs/)(\d+)", "gh"), (r"gh_jid=(\d+)", "gh"),
                     (r"ashbyhq\.com/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})", "ashby"), (r"lever\.co/[^/]+/([0-9a-f]{8}-[0-9a-f-]{27})", "lever"),
                     (r"myworkdayjobs\.com/.*_([a-z]*-?\d{4,}[a-z0-9-]*)$", "wd"), (r"workable\.com/[^/]+/j/([a-z0-9]+)", "workable")):
        m = re.search(pat, u)
        if m: return f"{pre}:{m.group(1)}"
    u = re.sub(r"^https?://(www\.)?", "", u).split("#")[0].split("?")[0].rstrip("/")
    return u or f"{_norm(company)}:{jid}"

def soft_key(job): return f"{_norm(job.get('company'))}|{_norm(job['title'])}"

# ---------------------------------- output ---------------------------------- #
def _sorted_groups(grouped):
    def newest(jobs): return min((age_days(j) if age_days(j) is not None else 9e9) for j in jobs)
    return sorted(grouped.items(), key=lambda kv: newest(kv[1]))

def _ordered(jobs): return sorted(jobs, key=lambda j: age_days(j) if age_days(j) is not None else 9e9)

def _split_recent(grouped, days=7):
    """Baseline email only. Gmail clips mail over 102 KB, so the email lists the <=7-day set (spec 3a, where the modifier is
    positive) and counts the older tiers. Nothing is dropped, latest_new.md carries every role."""
    recent, older = {}, {"8-30 days": 0, "31-90 days": 0, "90+ days": 0}
    for c, jobs in grouped.items():
        keep = []
        for j in jobs:
            d = age_days(j)
            if d is None or d <= days: keep.append(j)
            elif d <= 30: older["8-30 days"] += 1
            elif d <= 90: older["31-90 days"] += 1
            else: older["90+ days"] += 1
        if keep: recent[c] = keep
    return recent, older

STYLE = "<style>h3{margin:14px 0 4px}li{margin:2px 0}.t{background:#eef;padding:1px 5px;border-radius:3px;font-size:12px;margin-left:3px}.a{color:#555;font-size:12px}</style>"

def build_email(grouped, f, baseline=False):
    parts = [STYLE]
    if baseline:
        grouped, older = _split_recent(grouped)
        parts.append("<p>Baseline of currently open roles that pass the filters and were posted or updated in the last 7 days (spec 3a, the set where "
                     f"the age modifier is positive). Also tracked and never dropped, in latest_new.md in the repo: {older['8-30 days']} from 8-30 days, "
                     f"{older['31-90 days']} from 31-90 days, {older['90+ days']} older. Future emails contain only <b>newly opened</b> postings.</p>")
    else:
        parts.append("<p>These roles just opened. Age modifier in brackets is spec 3a on Interview probability.</p>")
    for company, jobs in _sorted_groups(grouped):
        parts.append(f"<h3>{escape(company)}</h3><ul>")
        for j in _ordered(jobs):
            loc = f" &mdash; {escape(j['location'])}" if j.get("location") else ""
            tg = "".join(f"<span class=t>{escape(x)}</span>" for x in tags(j, f))
            parts.append(f"<li><a href='{escape(j['url'])}'>{escape(j['title'])}</a>{loc} <span class=a>{escape(age_label(j))}</span>{tg}</li>")
        parts.append("</ul>")
    if DROPS: parts.append("<p style='color:#888;font-size:12px'>Filter drops this run: " + escape(drops_line()) + "</p>")
    parts.append("<p style='color:#888;font-size:12px'>Sent automatically by the job watcher. Score anything promising in the main workspace before building a package.</p>")
    return "\n".join(parts)

def build_markdown(grouped, f, baseline=False):
    out = [f"# Job watcher, {'baseline' if baseline else 'new roles'}, {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    for company, jobs in _sorted_groups(grouped):
        out.append(f"## {company}")
        for j in _ordered(jobs):
            loc = f" ({j['location']})" if j.get("location") else ""
            out.append(f"- [{j['title']}]({j['url']}){loc}. {age_label(j)}. {'; '.join(tags(j, f))}")
        out.append("")
    if DROPS: out += ["Filter drops this run. " + drops_line(), ""]
    return "\n".join(out)

def drops_line():
    return ", ".join(f"{k}={len(v)}" for k, v in sorted(DROPS.items(), key=lambda kv: -len(kv[1]))[:14])

def send_email(subject, html):
    if DRY_RUN:
        open("preview.html", "w", encoding="utf-8").write(html); print(f"DRY RUN: {subject!r} -> preview.html"); return
    user, pw, to = os.environ.get("SMTP_USERNAME"), os.environ.get("SMTP_PASSWORD"), os.environ.get("EMAIL_TO")
    if not (user and pw and to): sys.exit("set SMTP_USERNAME, SMTP_PASSWORD (Gmail App Password), EMAIL_TO")
    tos = [a.strip() for a in re.split(r"[,;\s]+", to) if a.strip()]
    msg = MIMEMultipart("alternative"); msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(tos)
    msg.attach(MIMEText(html, "html", "utf-8"))
    for attempt in range(3):
        try:
            with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), int(os.environ.get("SMTP_PORT", "465")), timeout=TIMEOUT) as s:
                s.login(user, pw); s.sendmail(user, tos, msg.as_string())
            print(f"Email sent to {tos}: {subject}"); return
        except (smtplib.SMTPException, OSError) as e:
            print(f"  ! SMTP attempt {attempt+1}: {e}"); time.sleep(5 * (attempt + 1))
    raise RuntimeError("SMTP failed 3x")

# ---------------------------------- main ------------------------------------ #
def main():
    global FILTERS
    cfg = load_json(CONFIG_FILE, None) or sys.exit("config.json missing")
    FILTERS = f = cfg.get("filters", {})
    seen = load_json(SEEN_FILE, {})
    meta = seen.setdefault("_meta", {})
    first_run, current, kept_by_soft, dupes, new = not meta.get("baseline_done"), {}, {}, {}, {}
    firms = [x for x in cfg["firms"] if x.get("enabled", True)]

    def poll(firm):
        try: return firm, FETCHERS[firm["ats"]](firm)
        except Exception as e:   # one dead board never kills the run
            print(f"  x {firm.get('name')} skipped: {e}"); return firm, []
    with ThreadPoolExecutor(max_workers=12) as pool:   # keep this parallel; 100+ boards serially takes an hour
        results = list(pool.map(poll, firms))

    # Direct boards first, trackers last, so a job reached both ways keeps the board's URL and body.
    big = int(f.get("big_board_jobs", 60))
    for firm, jobs in sorted(results, key=lambda r: r[0]["ats"] == "github_json"):
        # mode "entry" = require an entry-level signal (auto for boards with big_board_jobs+ live jobs). "all" = keep every
        # passing role (small startup boards, trackers, Workday boards whose search already narrows to new grad).
        mode = firm.get("mode") or ("entry" if firm["ats"] != "github_json" and len(jobs) >= big else "all")
        for j in jobs: j.setdefault("company", firm["name"]); j["_mode"] = mode
        rel = [j for j in jobs if is_relevant(j, f)]
        print(f"  ok {firm['name']}: {len(jobs)} jobs, {len(rel)} relevant")
        for j in rel:
            key, sk = canon_key(j.get("url"), j["company"], j["id"]), soft_key(j)
            if key in current: continue
            if j.get("tracker") and sk in kept_by_soft:
                # A tracker row that repeats a company+title already kept (from the board, or another tracker row) folds
                # into that line. Locations merge, so one Palantir new-grad req reads once with every city on it.
                k0, loc = kept_by_soft[sk], j.get("location") or ""
                if loc and loc.lower() not in (k0.get("location") or "").lower() and len(k0.get("location") or "") < 160:
                    k0["location"] = f"{k0['location']} | {loc}" if k0.get("location") else loc
                dupes[key] = j; continue
            current[key] = j; kept_by_soft.setdefault(sk, j)
            if key not in seen: new.setdefault(j["company"], []).append(j)
    if DROPS:   # log every drop; silent filtering is the most dangerous bug class
        print("Filter drops: " + drops_line())

    grouped = {} if first_run else new
    if first_run:
        for j in current.values(): grouped.setdefault(j["company"], []).append(j)
    total = sum(len(v) for v in grouped.values())
    md = build_markdown(grouped, f, first_run)
    if total:
        send_email(f"[Job Watcher] {'Baseline: ' if first_run else ''}{total} {'open' if first_run else 'new'} role(s)", build_email(grouped, f, first_run))
    else:
        print("No new roles this run.")
    open("preview.md" if DRY_RUN else LATEST_MD, "w", encoding="utf-8").write(md)
    print(f"Tracked {len(current)} relevant live roles ({len(dupes)} tracker duplicates folded in), {len(seen) - 1} seen before, {total} {'in baseline' if first_run else 'new'}.")
    if not DRY_RUN:
        for k, j in list(current.items()) + list(dupes.items()):
            seen.setdefault(k, {"title": j["title"], "url": j.get("url", ""), "company": j["company"], "first_seen": f"{datetime.now(timezone.utc):%Y-%m-%d}"})
        meta.update({"baseline_done": True, "last_run": f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M}Z"})
        save_json(SEEN_FILE, seen)

def seed(app_dir):
    """Mark every application_url already packaged in the main workspace as seen."""
    import glob
    seen = load_json(SEEN_FILE, {}); meta = seen.setdefault("_meta", {}); n = 0
    for p in sorted(glob.glob(os.path.join(app_dir, "*", "06_application_spec.json"))):
        s = load_json(p, {}) or {}
        folder = os.path.basename(os.path.dirname(p))
        for u in {s.get("application_url"), s.get("apply_url"), s.get("job_url"), s.get("posting_url")} - {None, ""}:
            k = canon_key(u)
            if k not in seen:
                seen[k] = {"title": folder, "url": u, "company": folder.split("_")[1] if "_" in folder else folder, "seeded_from": folder, "status": s.get("status", "")}; n += 1
    meta["seeded"] = meta.get("seeded", 0) + n; meta["seeded_at"] = f"{datetime.now(timezone.utc):%Y-%m-%d}"
    save_json(SEEN_FILE, seen); print(f"Seeded {n} already-packaged roles into {SEEN_FILE} ({len(seen) - 1} entries total).")

def probe(names):
    """Guess board tokens from company names and tell you which ATS each uses."""
    for n in names:
        slug = re.sub(r"[^a-z0-9]", "", n.lower()); hit = False
        for tok in (slug, slug + "inc", slug + "ai", slug + "careers", slug + "hq", slug.replace("ai", "-ai"), n.lower().replace(" ", "-")):
            for ats in ("greenhouse", "lever", "ashby", "workable"):
                try:
                    jobs = FETCHERS[ats]({"token": tok})
                    if jobs: print(f'  {n}: {{"name": "{n}", "ats": "{ats}", "token": "{tok}"}}  ({len(jobs)} postings)'); hit = True; break
                except Exception: pass
            if hit: break
        if not hit: print(f"  {n}: no public board found (Workday? JS careers page? set a native alert there)")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "probe": probe(sys.argv[2:])
    elif len(sys.argv) > 2 and sys.argv[1] == "seed": seed(sys.argv[2])
    else: main()
