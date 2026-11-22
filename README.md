# job-scout-feed

Daily scraper for co-op/internship postings in Canada. A GitHub Action (weekdays, early morning Toronto time) pulls public job lists and company job boards, drops clear mismatches, removes duplicates and publishes a compact daily batch in `out/batches/`.

Sources: SimplifyJobs (Winter 2027 term), Canadian-Tech-Internships-2027 (negarprh, coawp-com), Canadian-Engineering-Internships-2027 (coawp-com), Ashby/Lever/Greenhouse/Workable/SmartRecruiters boards for the companies in `companies.json` (board names looked up automatically each week), Hacker News "Who is Hiring" (monthly), Intern Insider newsletter (weekly).

Settings: `config.json` (term, age limit, batch size). Boards: `companies.json` (`token=Name`). Source errors: `state/health.json`.
