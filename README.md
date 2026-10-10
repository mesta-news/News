# Daily Digest

A private daily news digest for the two of us. It covers:

| Section | What it tracks |
|---|---|
| 🩺 Foreign doctors & BIG registration | News about the BIG-register, the foreign-diploma procedure (CIBG / CBGV), AKV-/BI-toets, language requirements, law changes and timelines. It also **watches the official BIG-register pages** and shows exactly what changed. |
| 🏥 Dutch healthcare job market | Shortages, ANIOS/basisarts hiring, collective agreements (cao), training places |
| 🤖 AI – models, tools & techniques | Model releases and capabilities, developer tools and practical techniques (OpenAI, Google, Hugging Face, Simon Willison, Latent Space, Hacker News, Google News on Anthropic/Claude) |
| 📈 Watchlist | Prices (1D/1W/1M/YTD and a 3-month sparkline) and headlines for Wolters Kluwer, ASML, Nvidia, Microsoft, Alphabet, Amazon, Meta, TSMC, the S&P 500, Nasdaq 100, AEX and EUR/USD |
| 🏦 Interest rates & central banks | ECB, Fed and Bank of England announcements plus news on the BoJ, PBoC and SNB, and Dutch mortgage and savings rates. Tiles show the policy rates and bond yields (US 2y/10y, German Bund, Dutch DSL) with 1-month and 1-year changes, from FRED |
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
3. **Connect Claude** (optional, but this is what turns a list of links into
   a briefing). Two options:
   * **Your Claude Pro/Max subscription (no extra cost):** install Claude Code
     on your computer (<https://claude.ai/download> or
     `npm install -g @anthropic-ai/claude-code`), run `claude setup-token` in a
     terminal, log in, and copy the token it prints (`sk-ant-oat…`). Then
     *Settings → Secrets and variables → Actions → New repository secret*
     → name `CLAUDE_CODE_OAUTH_TOKEN`. It counts toward your plan's usage
     limits (a small daily amount). The token gives access to your Claude
     account, so keep it only in GitHub Secrets.
   * **Pay-as-you-go API:** create a key at <https://console.anthropic.com>
     and save it as the secret `ANTHROPIC_API_KEY` (see *Cost* below).

   Without either, the digest still works, with headlines and snippets only.
4. **Run it:** *Actions → Daily digest → Run workflow*. After 2–3 minutes the
   site is live at `https://<your-username>.github.io/<repo-name>/`.
   **Install it as an app** to get a home-screen icon, a full-screen view and
   offline reading of the last edition:
   * **iPhone:** open the link in Safari → Share → *Add to Home Screen*.
   * **Android:** open it in Chrome → ⋮ menu → *Install app* (or *Add to Home screen*).
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
* **`rates`**: interest-rate series from [FRED](https://fred.stlouisfed.org); the ID is in the series page URL.
* **`model` / `effort`**: the Claude model and how hard it thinks.

Changes to `config.yaml` on `main` trigger a fresh digest automatically.

## Running locally

```bash
pip install -r requirements.txt
export CLAUDE_CODE_OAUTH_TOKEN=...  # optional (or ANTHROPIC_API_KEY=...)
python -m news_digest               # writes _site/index.html
python -m news_digest --no-ai       # skip Claude
```

## Cost

GitHub Actions and Pages are free for this. With `CLAUDE_CODE_OAUTH_TOKEN`
the summaries run on your Claude subscription at no extra cost. The Claude API is billed
separately from a Claude.ai subscription (prepaid credits at
console.anthropic.com). Rough cost of the daily digest (about six small
requests with headlines only), set with `model:` in `config.yaml`:

| Model | Approx. per month |
|---|---|
| `claude-opus-5-5` (default, best judgement) | ~$5–10 |
| `claude-sonnet-5-5` | ~$3–5 |
| `claude-haiku-5-5` | under $1 |

Without an API key the digest still runs for free, with headlines only.
