#!/usr/bin/env python3
"""job-scout-feed: fetch external co-op postings, drop clear Skips, dedupe, and publish a
compact daily batch for Claude to score. Stdlib only. All state lives here (Claude only reads).

  python scout.py fetch                          # GitHub Action: feeds -> out/batches/<date>.{txt,json}
  python scout.py finalize scores.txt b1.json ...  # Claude: scores -> sheet_rows.json + summary.txt (cwd)
"""
import datetime as dt, hashlib, html, json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(ROOT, *a)
CFG = json.load(open(P("config.json")))
TERM = f'{CFG["term"]["season"]} {CFG["term"]["year"]}'
TODAY = dt.date.today()
UA = {"User-Agent": "job-scout/1.0 (personal co-op search)"}
HEALTH = {"ok": {}, "errors": {}}


# ---------- io helpers ----------
def load(path, default):
    try:
        return json.load(open(P(path)))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def save(path, obj):
    os.makedirs(os.path.dirname(P(path)), exist_ok=True)
    with open(P(path), "w") as f:
        json.dump(obj, f, ensure_ascii=False, indent=0 if path.startswith("state") else None, separators=(",", ":"))

def get(url, as_json=False, timeout=25, data=None, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
        return (json.loads(body) if as_json else body), r.geturl()

def note(src, ok=None, err=None):
    if err is not None:
        HEALTH["errors"][src] = str(err)[:120]
    else:
        HEALTH["ok"][src] = ok


# ---------- normalising ----------
SUFFIX = r"\b(inc|ltd|llc|ulc|corp|corporation|limited|co|company|technologies|technology|group|canada)\b\.?"
def norm_company(c):
    c = re.sub(SUFFIX, " ", (c or "").lower())
    return re.sub(r"[^a-z0-9]+", "", c)

def norm_title(t):
    t = (t or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.sub(r"\b(winter|summer|fall|spring|20\d\d|\d+\s*-?\s*(?:to|or|-)?\s*\d*\s*months?|intern(ship)?s?|co-?op|student|usa?|canada|remote)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)

def key(c, t):
    return norm_company(c) + "|" + norm_title(t)

def hk(k):
    return hashlib.sha1(k.encode()).hexdigest()[:12]

def pid(board, k):
    return board.split("+")[0][:3] + "-" + hashlib.sha1(k.encode()).hexdigest()[:8]

def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</(p|li|div|h\d)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t\r\f\v]+", " ", s)

JD_KEYS = re.compile(r"(?i)(month|term|winter|january|jan\.?\s|co-?op|intern|require|qualif|must|you have|you'll need|experience with|proficien|year of|students?|degree|phd|master|python|c\+\+|typescript|react|ml\b|machine learning|robot|embedded|location|remote|hybrid|on-?site|visa|sponsor|citizen|clearance|deadline)")
def trim_jd(text, n=None):
    n = n or CFG["jd_chars"]
    text = re.sub(r"https?://\S+", "", strip_html(text))
    lines = [l.strip(" -•*\t") for l in re.split(r"\n|(?<=[.;])\s+", text)]
    keep = [l for l in lines if 12 < len(l) < 260 and JD_KEYS.search(l)]
    out, total = [], 0
    for l in keep:
        if l in out:
            continue
        out.append(l); total += len(l) + 2
        if total > n:
            break
    return " | ".join(out)[:n]


# ---------- clear-Skip rules (anything unsure goes to Claude) ----------
CA = re.compile(r"(?i)\bcanada\b|\b(ON|BC|QC|AB|MB|SK|NS|NB|NL|PE)\b(,|$|\s)|toronto|waterloo|kitchener|ottawa|vancouver|montr[eé]al|calgary|edmonton|mississauga|markham|burnaby|halifax|winnipeg|quebec|victoria, bc|oakville|guelph|hamilton")
US = re.compile(r"(?i)\b(usa|united states|u\.s\.)\b|,\s*(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b|new york|san francisco|seattle|boston|austin|chicago|bay area|palo alto|mountain view")
REMOTE = re.compile(r"(?i)remote|anywhere|distributed")

def loc_class(loc):
    loc = loc or ""
    if CA.search(loc):
        return "ca"
    if US.search(loc):
        return "us"
    if REMOTE.search(loc) or not loc.strip():
        return "?"
    return "other"

BAD_TITLE = re.compile(r"(?i)\b(senior|sr\.?|staff|principal|lead|manager|director|head of|new grad|graduate program|phd|ph\.d|postdoc|doctoral|master'?s|mba|full[- ]time|sales|marketing|account(ing|ant)|finance|financial|tax|audit|legal|counsel|recruit|talent|human resources|\bhr\b|people ops|communications|graphic|ux|ui designer|product design|visual design|help ?desk|service desk|it support|desktop support|security|cyber|soc analyst|data analyst|business analyst|financial analyst|business development|supply chain|procurement|mechanical|civil|chemical|biomedical|process engineer|geolog|construction|architectural|clinical|nurs|pharma|actuar|investment|banking|trader|operations specialist|customer success|support specialist|estimat\w*|planner|operator|technician|machinist|structural|stress|revenue|coordinator|assistant|administrat\w*|scheduler|buyer|inventory)\b")
INTERNISH = re.compile(r"(?i)intern|co-?op|student|stage|stagiaire|placement")

def months_in(text):
    out = []
    for grp in re.findall(r"(?i)((?:\b\d{1,2}\s*(?:,|-|–|to|or|and|/)?\s*(?:or\s+)?)+)\s*-?\s*months?\b", text or ""):
        out += [int(n) for n in re.findall(r"\d{1,2}", grp)]
    return [m for m in out if 1 <= m <= 24]

def term_skip(term_text):
    """True only when a term is stated and it clearly isn't the target term."""
    t = (term_text or "").lower()
    seasons = re.findall(r"(winter|summer|fall|autumn|spring)\s*(?:/\s*\w+\s*)?(20\d\d)?", t)
    if seasons:
        target_s, target_y = CFG["term"]["season"].lower(), str(CFG["term"]["year"])
        if not any(s == target_s and (y in ("", target_y)) for s, y in seasons) and "january" not in t and "jan 20" not in t:
            return True
    ms = set(months_in(t))
    if ms and min(ms) > CFG["term"]["months"]:
        return True
    return False

def too_old(posted):
    return posted is not None and (TODAY - posted).days > CFG["max_age_days"]

def make(board, company, title, loc, term, posted, url, jd=""):
    k = key(company, title)
    return {"id": pid(board, k), "k": k, "b": board, "c": company.strip(), "t": title.strip(),
            "l": (loc or "").strip()[:80], "lc": loc_class(loc), "term": (term or "").strip()[:40],
            "d": posted.isoformat() if posted else "", "u": url or "", "jd": jd}

def clear_skip(p):
    if p["lc"] == "other":
        return "location"
    if BAD_TITLE.search(p["t"]):
        return "field/level"
    if term_skip(p["term"] + " " + p["t"]):
        return "term"
    if p["d"] and too_old(dt.date.fromisoformat(p["d"])):
        return "old"
    return None


# ---------- sources ----------
def src_simplify():
    data, _ = get(CFG["sources"]["simplify"], as_json=True, timeout=60)
    out = []
    for x in data:
        if not x.get("active") or not x.get("is_visible", True) or TERM not in x.get("terms", []):
            continue
        posted = dt.date.fromtimestamp(x.get("date_posted") or 0)
        loc = "; ".join(x.get("locations") or [])
        p = make("simplify", x["company_name"], x["title"], loc, ", ".join(x["terms"]), posted, x.get("url"))
        if p["lc"] == "us" and x.get("sponsorship") == "U.S. Citizenship is Required":
            continue
        if p["lc"] == "us" and x.get("sponsorship") == "Does Not Offer Sponsorship":
            p["no_sponsor"] = True
        out.append(p)
    return out

def parse_date(s):
    s = re.sub(r"<.*?>", "", s or "").replace("\xa0", " ").strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    for fmt in ("%b %d %Y", "%B %d %Y"):  # "Nov 8": no year given
        try:
            d = dt.datetime.strptime(f"{s} {TODAY.year}", fmt).date()
            return d.replace(year=TODAY.year - 1) if d > TODAY else d
        except ValueError:
            pass
    return None

def md_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]

def md_link(cell):
    links = [u for u in re.findall(r"\]\((https?://[^)\s]+)\)", cell) if "img.shields.io" not in u]
    return links[-1] if links else ""

def md_text(cell):
    cell = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cell)
    cell = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cell)
    cell = re.sub(r"<br\s*/?>", "; ", cell)
    return html.unescape(re.sub(r"<[^>]+>|\*\*", "", cell)).replace("\xa0", " ").replace("\u200b", "").strip()

def src_negarprh():
    text, _ = get(CFG["sources"]["cti_negarprh"])
    out = []
    for line in text.splitlines():
        cells = md_cells(line)
        if len(cells) < 5 or cells[0] in ("Company",) or set(cells[0]) <= set("-: "):
            continue
        if "🔒" in line or "closed" in line.lower():
            continue
        company, role, loc, apply, date = md_text(cells[0]), md_text(cells[1]), md_text(cells[2]), cells[3], md_text(cells[4])
        m = re.search(r"\(([^)]*(?:20\d\d|winter|summer|fall|month)[^)]*)\)", role, re.I)
        out.append(make("cti", company, role, loc, m.group(1) if m else "", parse_date(date), md_link(apply)))
    return out

def src_coawp(name):
    text, _ = get(CFG["sources"][name])
    out, section, last_co = [], None, ""
    eng_ok = re.compile(r"(?i)software|firmware|embedded|robot|autonom|computer|\bai\b|machine learning|\bml\b|automation|controls?\b|fpga|asic|hardware|verification|validation|test|mechatronic|vision|perception|systems|developer|programm|data")
    for line in text.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not section or not any(s.lower() in section.lower() for s in CFG["coawp_sections"]):
            continue
        cells = md_cells(line)
        if len(cells) < 6 or cells[0] == "Company" or set(cells[0]) <= set("-: "):
            continue
        company = md_text(cells[0])
        if company.startswith("↳") or not company:
            company = last_co
        last_co = company
        if name == "coawp_eng" and not eng_ok.search(md_text(cells[1])):
            continue
        term = md_text(cells[3]).replace("—", "")
        out.append(make("coawp", company, md_text(cells[1]), md_text(cells[2]), term, parse_date(md_text(cells[4])), md_link(cells[5])))
    return out

def ats_jobs(kind, tok):
    out = []
    if kind == "ashby":
        d, _ = get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}", as_json=True)
        for j in d.get("jobs", []):
            loc = "; ".join([j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []])
            if j.get("isRemote"):
                loc += " (remote)"
            posted = parse_date((j.get("publishedAt") or "")[:10])
            out.append((tok, j.get("title", ""), loc, posted, j.get("jobUrl"), j.get("descriptionPlain") or j.get("descriptionHtml") or ""))
    elif kind == "lever":
        d, _ = get(f"https://api.lever.co/v0/postings/{tok}?mode=json", as_json=True)
        for j in d:
            cat = j.get("categories") or {}
            loc = "; ".join(cat.get("allLocations") or [cat.get("location") or ""]) + (" (remote)" if j.get("workplaceType") == "remote" else "")
            posted = dt.date.fromtimestamp((j.get("createdAt") or 0) / 1000)
            body = (j.get("descriptionPlain") or "") + " " + " ".join(strip_html(l.get("content", "")) for l in j.get("lists") or [])
            out.append((tok, j.get("text", ""), loc, posted, j.get("hostedUrl"), body))
    elif kind == "workable":
        d, _ = get(f"https://apply.workable.com/api/v3/accounts/{tok}/jobs", as_json=True, data=b'{"query":"","location":[],"department":[],"worktype":[],"remote":[]}', headers={"Content-Type": "application/json"})
        for j in d.get("results", []):
            loc = j.get("location") or {}
            locs = "; ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])) + (" (remote)" if j.get("remote") else "")
            out.append((tok, j.get("title", ""), locs, parse_date((j.get("published") or "")[:10]), f"https://apply.workable.com/{tok}/j/{j.get('shortcode')}/", ""))
    elif kind == "smartrecruiters":
        d, _ = get(f"https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit=100", as_json=True)
        for j in d.get("content", []):
            loc = j.get("location") or {}
            locs = "; ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])) + (" (remote)" if loc.get("remote") else "")
            out.append((tok, j.get("name", ""), locs, parse_date((j.get("releasedDate") or "")[:10]), f"https://jobs.smartrecruiters.com/{tok}/{j.get('id')}", ""))
    else:
        d, _ = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true", as_json=True)
        for j in d.get("jobs", []):
            posted = parse_date((j.get("first_published") or j.get("updated_at") or "")[:10])
            out.append((tok, j.get("title", ""), (j.get("location") or {}).get("name", ""), posted, j.get("absolute_url"), html.unescape(j.get("content") or "")))
    return out

ATS_KINDS = ("ashby", "lever", "greenhouse", "workable", "smartrecruiters")

def probe(kind, slug):
    """True if this job-board account exists and has at least one posting."""
    try:
        if kind == "ashby":
            d, _ = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", as_json=True, timeout=12); return bool(d.get("jobs"))
        if kind == "lever":
            d, _ = get(f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1", as_json=True, timeout=12); return isinstance(d, list) and bool(d)
        if kind == "greenhouse":
            d, _ = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", as_json=True, timeout=12); return bool(d.get("jobs"))
        if kind == "workable":
            d, _ = get(f"https://apply.workable.com/api/v3/accounts/{slug}/jobs", as_json=True, timeout=12, data=b'{"query":""}', headers={"Content-Type": "application/json"}); return bool(d.get("results"))
        if kind == "smartrecruiters":
            d, _ = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", as_json=True, timeout=12); return bool(d.get("content"))
    except Exception:
        return False
    return False

def slugs(name):
    base = re.sub(r"\(.*?\)", "", name).lower().replace("&", "and").replace(".", "")
    words = re.findall(r"[a-z0-9]+", base)
    out = ["".join(words), "-".join(words)]
    if len(words) > 1 and words[-1] in ("ai", "inc", "labs", "technologies", "robotics", "app", "hq", "com"):
        out.append("".join(words[:-1]))
    return list(dict.fromkeys(o for o in out if o))

def discover_boards(comps):
    """Weekly (or when the name list changes): find which ATS each company in comps['discover'] uses."""
    names = comps.get("discover", [])
    state = load("state/boards.json", {})
    sig = hashlib.sha1("|".join(names).encode()).hexdigest()[:10]
    if state.get("sig") == sig and state.get("week") == TODAY.strftime("%G-W%V"):
        return state.get("found", {})
    jobs = [(n, k, sl) for n in names for sl in slugs(n) for k in ATS_KINDS]
    with ThreadPoolExecutor(16) as ex:
        hits = list(ex.map(lambda t: t if probe(t[1], t[2]) else None, jobs))
    found, got = {k: [] for k in ATS_KINDS}, set()
    for h in hits:
        if h and h[0] not in got:
            got.add(h[0]); found[h[1]].append(f"{h[2]}={h[0]}")
    state = {"sig": sig, "week": TODAY.strftime("%G-W%V"), "found": found,
             "missing": sorted(set(names) - got)}
    save("state/boards.json", state)
    note("discover", ok=f"{len(got)}/{len(names)} companies found")
    return found

def src_ats():
    comps = load("companies.json", {})
    found = discover_boards(comps)
    names = {}
    tasks = []
    for k in ATS_KINDS:
        for entry in comps.get(k, []) + found.get(k, []):
            if entry.partition("=")[0] in names:
                continue
            tok, _, name = entry.partition("=")
            names[tok] = name or tok.replace("-", " ").title()
            tasks.append((k, tok))
    def run(kt):
        try:
            jobs = ats_jobs(*kt)
            note(f"{kt[0]}:{kt[1]}", ok=len(jobs))
            return kt[0], jobs
        except Exception as e:
            note(f"{kt[0]}:{kt[1]}", err=e)
            return kt[0], []
    out = []
    with ThreadPoolExecutor(8) as ex:
        for kind, jobs in ex.map(run, tasks):
            for tok, title, loc, posted, url, body in jobs:
                if not INTERNISH.search(title):
                    continue
                term = " ".join(re.findall(r"(?i)(?:winter|summer|fall|spring)\s*20\d\d|\d{1,2}\s*(?:-|to|or)?\s*\d{0,2}\s*-?\s*months?", title + " " + strip_html(body)[:3000]))
                out.append(make(kind, names[tok], title, loc, term, posted, url, trim_jd(body)))
    return out

def src_hn():
    state = load("state/hn.json", {})
    month = TODAY.strftime("%Y-%m")
    if state.get("done") == month or TODAY.day > 7:
        return []
    hits, _ = get("https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&query=who%20is%20hiring", as_json=True)
    story = next((h for h in hits.get("hits", []) if "who is hiring" in h.get("title", "").lower()), None)
    if not story or not story.get("created_at", "").startswith(month):
        return []
    item, _ = get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}", as_json=True, timeout=60)
    out = []
    for c in item.get("children", []):
        txt = strip_html(c.get("text") or "")
        if not re.search(r"(?i)\bintern(ship)?s?\b|co-?op\b", txt) or not re.search(r"(?i)canada|toronto|waterloo|vancouver|montr[eé]al|ottawa|remote", txt):
            continue
        head = txt.split("\n")[0]
        parts = [s.strip() for s in head.split("|")]
        company = parts[0][:60] if parts else "HN"
        loc = next((s for s in parts if CA.search(s) or REMOTE.search(s) or US.search(s)), "")
        out.append(make("hn", company, "Intern (HN Who is Hiring)", loc, " ".join(months_in(txt) and [f"{m} months" for m in months_in(txt)]), TODAY, f"https://news.ycombinator.com/item?id={c['id']}", trim_jd(txt, 600)))
    state["done"] = month
    save("state/hn.json", state)
    return out

def src_interninsider():
    """Weekly newsletter; its issues are public web pages. Takes only the tech section."""
    state = load("state/interninsider.json", {})
    home, base = get(CFG["sources"]["interninsider"])
    posts = re.findall(r'href="((?:https://newsletter\.interninsider\.me)?/p/[\w-]+)"', home)
    if not posts:
        raise RuntimeError("no posts found on newsletter home page")
    url = posts[0] if posts[0].startswith("http") else "https://newsletter.interninsider.me" + posts[0]
    if state.get("last") == url:
        return []
    page, _ = get(url)
    m = re.search(r"(?is)Tech Internships(.*?)(Business Internships|$)", page)
    part = m.group(1) if m else page
    out = []
    for li in re.findall(r"(?is)<li[^>]*>(.*?)</li>", part):
        href = re.search(r'href="(https?://[^"]+)"', li)
        text = re.sub(r"\s+", " ", strip_html(li)).strip()
        mm = re.match(r"(.+?)\s+@\s+(.+?)\s+[–-]\s+(.+)$", text)
        if not href or not mm or "interninsider" in href.group(1):
            continue
        title, company, loc = mm.groups()
        out.append(make("interninsider", company, title, loc, "", TODAY, html.unescape(href.group(1))))
    state["last"] = url
    save("state/interninsider.json", state)
    return out


# ---------- enrichment for list sources (no JD) + dead-page check ----------
WD = re.compile(r"https://([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/]+)/job/(.+)")
def enrich(p):
    u = p["u"]
    if not u or p["jd"]:
        return p
    try:
        m = WD.match(u)
        if m:
            d, _ = get(f"https://{m[1]}.{m[2]}.myworkdayjobs.com/wday/cxs/{m[1]}/{m[3]}/job/{m[4]}", as_json=True)
            p["jd"] = trim_jd((d.get("jobPostingInfo") or {}).get("jobDescription", ""))
            return p
        gh = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", u)
        if gh:
            d, _ = get(f"https://boards-api.greenhouse.io/v1/boards/{gh[1]}/jobs/{gh[2]}", as_json=True)
            p["jd"] = trim_jd(html.unescape(d.get("content", "")))
            return p
        lv = re.search(r"jobs\.lever\.co/([\w-]+)/([0-9a-f-]{36})", u)
        if lv:
            d, _ = get(f"https://api.lever.co/v0/postings/{lv[1]}/{lv[2]}", as_json=True)
            p["jd"] = trim_jd((d.get("descriptionPlain") or "") + " " + " ".join(strip_html(l.get("content", "")) for l in d.get("lists") or []))
            return p
        page, final = get(u, timeout=20)
        p["u"] = final if "coawp.com/go" in u else u
        if re.search(r"(?i)(no longer (accepting|available)|position (has been )?(filled|closed)|job (is )?(closed|expired)|page not found)", page[:20000]):
            p["dead"] = True
        p["jd"] = trim_jd(page)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            p["dead"] = True
    except Exception:
        pass
    return p


# ---------- commands ----------
def cmd_fetch():
    seen = load("state/seen.json", {})          # hashed key -> date first batched
    pending = load("state/pending.json", [])    # passed the rules, waiting for a batch slot
    pend_keys = {p["k"] for p in pending}
    raw, counts = [], {}
    for name, fn in [("simplify", src_simplify), ("cti", src_negarprh), ("coawp_tech", lambda: src_coawp("coawp_tech")),
                     ("coawp_eng", lambda: src_coawp("coawp_eng")), ("ats", src_ats), ("hn", src_hn),
                     ("interninsider", src_interninsider)]:
        try:
            got = fn()
            counts[name] = len(got)
            note(name, ok=len(got))
            raw += got
        except Exception as e:
            counts[name] = "ERR"
            note(name, err=e)
    merged, skipped = {}, {}
    for p in raw:
        if hk(p["k"]) in seen or p["k"] in pend_keys:
            continue
        if p["k"] in merged:
            m = merged[p["k"]]
            if p["b"] not in m["b"].split("+"):
                m["b"] += "+" + p["b"]
            for f in ("jd", "term", "l", "d"):
                if not m.get(f) and p.get(f):
                    m[f] = p[f]
            continue
        why = clear_skip(p)
        if why:
            skipped[why] = skipped.get(why, 0) + 1
            continue
        merged[p["k"]] = p
    new = list(merged.values())
    with ThreadPoolExecutor(8) as ex:
        new = list(ex.map(enrich, new))
    dead = sum(1 for p in new if p.get("dead"))
    keep = []
    for p in new:
        if p.get("dead"):
            continue
        if not p["term"] and term_skip(p["jd"]) and not re.search(r"(?i)winter|january|\b4[- ]month", p["jd"]):
            skipped["term(jd)"] = skipped.get("term(jd)", 0) + 1
            continue
        keep.append(p)
    pool = pending + keep
    pool = [p for p in pool if not (p["d"] and too_old(dt.date.fromisoformat(p["d"])))]
    pool.sort(key=lambda p: (p["lc"] == "us", -(dt.date.fromisoformat(p["d"]).toordinal() if p["d"] else TODAY.toordinal())))

    # today's batch (a re-run on the same day adds to it)
    bpath = f"out/batches/{TODAY.isoformat()}.json"
    batch = load(bpath, {"date": TODAY.isoformat(), "items": []})
    room = max(0, CFG["max_score_per_run"] - len(batch["items"]))
    batch["items"] += pool[:room]
    save("state/pending.json", pool[room:])
    for p in batch["items"]:
        seen.setdefault(hk(p["k"]), TODAY.isoformat())
    save("state/seen.json", seen)
    batch["stats"] = {"fetched": counts, "dropped": skipped, "dead": dead, "in_batch": len(batch["items"]), "waiting": len(pool[room:])}
    save(bpath, batch)
    write_prompt(batch)
    # keep only recent batches
    cutoff = TODAY - dt.timedelta(days=CFG.get("batch_keep_days", 7))
    for f in os.listdir(P("out", "batches")):
        try:
            if dt.date.fromisoformat(f[:10]) < cutoff:
                os.remove(P("out", "batches", f))
        except ValueError:
            pass
    dates = sorted({f[:10] for f in os.listdir(P("out", "batches")) if f.endswith(".json")})
    open(P("out", "index.txt"), "w").write("\n".join(dates) + "\n")
    save("state/health.json", HEALTH)
    print(json.dumps(batch["stats"]))

def write_prompt(batch):
    lines = [f"# batch {batch['date']}: {len(batch['items'])} candidates  (id | company | title | location [class] | term | posted | key lines)"]
    for p in batch["items"]:
        flag = " no-sponsor" if p.get("no_sponsor") else ""
        jd = (p["jd"] or "-")[:200] if p["lc"] == "us" else (p["jd"] or "-")
        lines.append(f'{p["id"]} | {p["c"]} | {p["t"]} | {p["l"]} [{p["lc"]}{flag}] | {p["term"] or "-"} | {p["d"] or "-"} | {jd}')
    open(P("out", "batches", batch["date"] + ".txt"), "w").write("\n".join(lines) + "\n")

def cmd_finalize(scores_path, batch_paths):
    by_id, stats, dates = {}, {}, []
    for bp in batch_paths:
        b = json.load(open(bp))
        dates.append(b["date"]); stats[b["date"]] = b.get("stats", {})
        for p in b["items"]:
            by_id[p["id"]] = p
    scored = []
    for line in open(scores_path):
        parts = [s.strip() for s in line.split("|")]
        if len(parts) < 4 or parts[0] not in by_id:
            continue
        p = dict(by_id[parts[0]])
        try:
            p["fit"] = int(float(parts[1]))
        except ValueError:
            continue
        p["v"], p["why"] = parts[2][:1].upper(), parts[3][:140]
        scored.append(p)
    unscored = len(by_id) - len(scored)
    fits = [p for p in scored if p["v"] in "AS" and p["fit"] >= CFG["fit_threshold"]]
    rank = lambda p: (p["v"] != "A", -p["fit"], p.get("d") or "")
    ca = sorted([p for p in fits if p["lc"] != "us"], key=rank)
    us = sorted([p for p in fits if p["lc"] == "us"], key=rank)
    def mdlink(t, u):
        t = re.sub(r"([\\\[\]*_~])", r"\\\1", t)
        return {"markdown": f"[{t}]({u})"} if u else t
    rows = [[mdlink(p["t"], p["u"]), p["c"], p["fit"], None, None, p["b"], ("Stretch: " if p["v"] == "S" else "") + p["why"],
             "'" + p["id"], TODAY.isoformat()] for p in ca]
    json.dump(rows, open("sheet_rows.json", "w"), ensure_ascii=False)
    L = [f"job-scout {TODAY:%a %b %d} (batch {', '.join(dates)}): {len(ca)} fit(s) added to your tracker."]
    for p in ca:
        L.append(f"\n[{p['fit']}/10 {'Apply' if p['v']=='A' else 'Stretch'}] {p['c']} - {p['t']} ({p['l'] or 'location ?'})\n  {p['why']}\n  {p['u']}  [{p['b']}]")
    if us:
        L.append(f"\nUS roles (needs J-1), not added to the tracker ({len(us)}):")
        for p in us:
            L.append(f"- [{p['fit']}/10] {p['c']} - {p['t']} ({p['l']}) {p['u']}" + (" (says no sponsorship)" if p.get("no_sponsor") else ""))
    for d, st in stats.items():
        L.append(f"\n{d}: scanned {st.get('fetched')} | dropped by rules {st.get('dropped')} | dead pages {st.get('dead')} | scored {st.get('in_batch')} | waiting for later batches {st.get('waiting')}")
    if unscored:
        L.append(f"Not scored: {unscored} (they won't come back automatically).")
    open("summary.txt", "w").write("\n".join(L))
    print(json.dumps({"rows": len(rows), "us": len(us), "scored": len(scored), "unscored": unscored}))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        cmd_fetch()
    elif cmd == "finalize":
        cmd_finalize(sys.argv[2], sys.argv[3:])
    else:
        print(__doc__)
