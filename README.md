# job-scout-feed

Daily scraper for co-op/internship postings in Canada. A GitHub Action (weekdays, early morning Toronto time) pulls public job lists and company job boards, drops clear mismatches, removes duplicates and publishes a compact daily batch in `out/batches/`.

Sources: SimplifyJobs (Winter 2027 term), Canadian-Tech-Internships-2027 (negarprh, coawp-com), Canadian-Engineering-Internships-2027 (coawp-com), Ashby/Lever/Greenhouse/Workable/SmartRecruiters boards for the companies in `companies.json` (board names looked up automatically each week), Hacker News "Who is Hiring" (monthly), Intern Insider newsletter (weekly).

Settings: `config.json` (term, age limit, batch size). Boards: `companies.json` (`token=Name`). Source errors: `state/health.json`.

Posting pages: every posting that passes the title/location/term rules has its own page read (Workday, Greenhouse, Lever, Ashby, SmartRecruiters, BambooHR, Oracle and UKG through their JSON; other sites as HTML, following aggregator redirects). The stated work term and the requirement lines go into a ~500-character summary for scoring. Postings are dropped automatically when the page states a different term or a longer one (e.g. "8 months", "January – June"), asks for 1+ years of experience (unless it's called an asset), sets a graduation window he isn't in (`grad_year` in config.json, "or later" dates are fine), or asks for completed 2+ years / third- or fourth-year standing. French is never a reason to drop. Each removal and the line that caused it are listed under `page_drops` in that day's batch JSON. If a page can't be read, the posting is kept, marked "requirements unknown" and capped at Stretch.
