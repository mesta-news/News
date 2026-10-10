# Daily Digest

A private daily news digest for the two of us. It covers:

| Section | What it tracks |
|---|---|
| 🩺 Foreign doctors & BIG registration | News about the BIG-register, the foreign-diploma procedure (CIBG / CBGV), AKV-/BI-toets, language requirements, law changes and timelines. It also **watches the official BIG-register pages** and shows exactly what changed. |
| 🏥 Dutch healthcare job market | Shortages, ANIOS/basisarts hiring, collective agreements (cao), training places |
| 🤖 AI – models, tools & techniques | Model releases and capabilities, developer tools and practical techniques (OpenAI, Google, Hugging Face, Simon Willison, Latent Space, Hacker News, Google News on Anthropic/Claude) |
| 📈 Watchlist | Prices (1D/1W/1M/YTD and a 3-month sparkline) and headlines for Wolters Kluwer, ASML, Nvidia, Microsoft, Alphabet, Amazon, Meta, TSMC, the S&P 500, Nasdaq 100, AEX and EUR/USD |
| 🌍 Business & markets | A Reuters/Bloomberg-style morning picture (Reuters and Bloomberg via Google News, CNBC, BBC, MarketWatch, NOS Economie) |

Every morning a GitHub Action collects the news, asks Claude to write a short
briefing per section ("what happened", "what it means for us", the best
articles), and publishes the result as a web page on GitHub Pages. You can
also have it emailed to you.

## How it works (and why not a JavaScript-only web app)

A web page running in the browser **cannot reliably read other websites**.
Browsers block cross-site requests (CORS) and most news sites don't allow
them. You also can't hide an API key in JavaScript that everyone can download.
So the collecting happens on a server, and the web page only shows the result:

```
 GitHub Actions (free, runs on a schedule every morning)
   1. read RSS feeds + Google News searches     news_digest/sources.py
   2. check official pages for changes          news_digest/pages.py
   3. get watchlist prices (Yahoo Finance)      news_digest/markets.py
   4. Claude writes the briefings (optional)    news_digest/summarize.py
   5. render HTML + save history (data/*.json)  news_digest/__main__.py
        │
        ├──► GitHub Pages website (phone / laptop)
        └──► email (optional)
```

**RSS feeds instead of scraping.** Almost every news site publishes an RSS
feed: a machine-readable list of its latest articles. Google News turns any
search, such as `"BIG-register" buitenlandse artsen`, into a feed too. That is
stable and legal, unlike scraping article HTML, which breaks whenever a site
changes its layout. The only pages the digest reads directly are the few
official pages it watches for changes.

## Setup (about 10 minutes)

1. **Make `main` the default branch.** If the code is on another branch, merge
   it into `main` or rename the branch to `main` (*Settings → Branches*).
   Scheduled workflows only run on the default branch.
2. **Turn on GitHub Pages:** *Settings → Pages → Build and deployment → Source:*
   **GitHub Actions**.
   GitHub Pages on a free account needs a **public** repo. The site only shows
   public news; your `profile` text is never published. It is, however,
   readable in `config.yaml` in a public repo, so keep it general or use a
   paid plan with a private repo.
3. **Add the Claude API key** (optional, but this is what turns a list of links
   into a briefing): create a key at <https://console.anthropic.com>, then
   *Settings → Secrets and variables → Actions → New repository secret*
   → name `ANTHROPIC_API_KEY`.
   Without it the digest still works, with headlines and snippets only.
4. **Run it:** *Actions → Daily digest → Run workflow*. After 2–3 minutes the
   site is live at `https://<your-username>.github.io/<repo-name>/`.
   Add it to both phones' home screens (Share → *Add to Home Screen*).
5. **Email (optional):** add these secrets: `SMTP_HOST` (e.g. `smtp.gmail.com`),
   `SMTP_USER` (your Gmail address), `SMTP_PASSWORD` (a Gmail
   [app password](https://myaccount.google.com/apppasswords), not your normal
   password) and `DIGEST_EMAIL_TO` (comma-separated, e.g. both your addresses).
   The scheduled run will then email the digest every morning.

## Customising

Everything is in [`config.yaml`](config.yaml):

* **`profile`**: who you are. Claude uses it to explain why something matters.
  Fill in the TODOs, especially where the diploma is from (EU/EEA or not).
  That determines which BIG procedure applies.
* **`sections`**: add or remove feeds and Google News queries. Queries support
  `OR`, `"exact phrase"`, `site:medischcontact.nl` and `-exclude`.
* **`watch_pages`**: official pages to monitor for changes.
* **`watchlist`**: Yahoo Finance symbols (Amsterdam stocks end in `.AS`).
* **`model` / `effort`**: the Claude model and how hard it thinks.

Changes to `config.yaml` on `main` trigger a fresh digest automatically.

## Running locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # optional
python -m news_digest               # writes _site/index.html
python -m news_digest --no-ai       # skip Claude
```

## Cost

GitHub Actions and Pages are free for this. Claude costs a few cents per daily
digest, since it sends about six small requests with headlines only, not full
articles. Use `effort: low` in `config.yaml` to make it cheaper.
