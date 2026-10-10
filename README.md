# Daily Digest

A private daily news digest for the two of us. It covers:

| Section | What it tracks |
|---|---|
| 💼 Careers, jobs & registration | Hiring, expansions and layoffs at CROs, pharma and biotech in the Netherlands (Utrecht, Leiden, Amsterdam), and demand for CRA, medical affairs, MSL, pharmacovigilance and medical-information roles. Also BIG-register news (only material changes) and a **watch on the official BIG-register pages** |
| 🔬 Clinical trials, regulation & medical affairs | EMA decisions, EU Clinical Trials Regulation / CTIS, ICH E6(R3) GCP, Dutch bodies (CCMO, CBG-MEB), drug safety, AI in clinical trials |
| 🧬 Medical science & research | NEJM, The Lancet, The BMJ, Nature Medicine and STAT, plus major trial readouts, FDA/EMA decisions and research from Dutch UMCs, explained for a physician moving into medical affairs |
| 🤖 AI – models, tools & techniques | Model releases and capabilities, developer tools and practical techniques (OpenAI, Google, Hugging Face, Simon Willison, Latent Space, Hacker News, Google News on Anthropic/Claude) |
| 📈 Watchlist | Prices (1D/1W/1M/YTD and a 3-month sparkline) and headlines for Wolters Kluwer, ASML, Nvidia, Microsoft, Alphabet, Amazon, Meta, TSMC, the S&P 500, Nasdaq 100, AEX and EUR/USD |
| 🏦 Interest rates & central banks | ECB, Fed and Bank of England announcements plus news on the BoJ, PBoC and SNB, and Dutch mortgage and savings rates. Tiles show the ECB deposit rate, €STR, Euribor, the euro AAA curve (2y/10y/30y), the Dutch 10y and US yields with 1-month and 1-year changes, from the ECB Data Portal and Yahoo Finance |
| 🏦 Dutch banking & ALM | Dutch banks (ING, ABN AMRO, Rabobank, de Volksbank, Brand New Day…), savings and mortgage rates, DNB / ECB / EBA supervision, IRRBB and liquidity regulation, the pension reform (Wtp) and the long end of the swap curve, the housing market. Tiles show Dutch new-mortgage and term-deposit rates and Dutch inflation; each briefing ends with an **On the radar** list of dated upcoming events |
| ⚡ Energy & commodities | Oil (Brent, WTI, OPEC+), Dutch TTF and US gas, LNG, EU carbon (ETS), power prices and Dutch energy news (energy bills, Gasunie, TenneT grid congestion). Tiles show Brent, WTI, TTF, Henry Hub, heating oil, Shell and TotalEnergies, plus euro-area and Dutch energy inflation |
| 🗞️ Netherlands, Morocco & the world | General news in three groups that take turns so each gets space: the Netherlands (NOS, NL Times, DutchNews), Morocco (Morocco World News, Hespress, Google News in English, French and Dutch) and major world news (BBC, Al Jazeera, Reuters) |
| 💻 Technology | Hardware and consumer tech outside AI: phones, laptops, chips, TVs, consoles, reviews, deals and EU tech rules (The Verge, Ars Technica, Engadget, Tom's Hardware, Tweakers) |
| 🎮 Gaming | GTA 6, Gran Turismo 7, Age of Empires, Red Dead, Cyberpunk 2077, Ghost of Tsushima/Yotei, PlayStation Plus and sales (IGN, GameSpot, PC Gamer and Eurogamer filtered to those games, PlayStation Blog, Xbox Wire, Google News) |
| 🌍 Business & markets | A Reuters/Bloomberg-style morning picture (Reuters and Bloomberg via Google News, CNBC, BBC, MarketWatch, NOS Economie) |

The page has one tab per section plus a **Today** front page; each phone remembers the last tab opened, so each reader lands on their own sections. Swipe left/right to change tabs (or use the arrow keys on a computer). Tap a price in the black ticker to jump to its tile.

Every morning a GitHub Action collects the news, asks Claude to write a short
briefing per section ("what happened", "what it means for us", the best
articles), and publishes the result as a web page on GitHub Pages. You can
also have it emailed to you.

## Depth

* **Coming up** on the Today page collects every tab's dated events (central bank meetings, data releases, launches, game releases) in date order.
* Some briefings end with an **Explainer**, a short background note on the one development that needs context.
* Claude sees each tab's previous briefing, so it flags follow-ups and reversals instead of repeating yesterday.
* **This week** (Saturday and Sunday editions): a week in review per tab, written from the week's saved briefings.
* **Reader**: tap any story to read it in the app: its picture, a short summary Claude wrote from the article, why it matters, then **Read the full article at the source**. Each morning the run opens the top stories of every tab (resolving Google News links to the publisher) so Claude can summarise them; only the summary and the picture link are stored, never the article text.
* **Search** (magnifier): stories and briefings from the last 90 days (`search.json`, built with the site).
* **Saved** (bookmark): tap ☆ on any story to keep it; saved stories stay on that phone.
* **For you**: the stories you open teach the app which topics and sources you like; up to two matching stories per tab move to the top. Stored on each phone only; reset in the footer.
* **Charts**: tap a price or rate tile for a 1-year chart; drag across it to read values.

* **Morning essentials** on Today: Utrecht weather (Open-Meteo; change `location:` in `config.yaml`) and the euro → dirham rate (tap for its chart in the World tab).
* **Listen**: ▶ on Today and on every tab reads the briefing aloud with the phone's own voice.
* **Calendar**: "＋ Add to my calendar" on Today subscribes your phone's calendar to `calendar.ics`, every dated "Coming up" event from the last three weeks; it updates itself.
* **Yield curve** (Rates): the euro AAA curve from 1 to 30 years today, a month ago and a year ago, with the 2s10s and 10s30s slopes.

## Privacy

This repo is public, so two optional switches keep your brief private:

* **Private data repo.** Create a private repo `<owner>/news-data` (or set the
  variable `DATA_REPO` to another name) and a fine-grained token with
  *Contents: Read and write* on only that repo, saved as the secret
  `DATA_REPO_TOKEN`. The next run moves `data/` and `state/` there and deletes
  them from this repo; after that the daily editions live only in the private
  repo. (Old copies remain in this repo's git history until it is rewritten.)
* **Passphrase (simplest: this alone is enough).** Set the secret
  `SITE_PASSPHRASE`. Every page and the search index are then published
  encrypted (AES-GCM, key from PBKDF2); each phone asks for the passphrase once
  and remembers the derived key ("Lock this phone" in Settings). The saved
  editions and state in `data/` and `state/` are also stored encrypted with it,
  so this public repo only holds ciphertext. Keep the passphrase somewhere safe:
  without it the saved history can't be read. The calendar feed and
  notifications are not encrypted.

## Settings

The ⚙️ icon opens per-phone settings: theme (System, Light, Dark), text size,
which tabs to show (hidden tabs also leave the Today page and the swipe order),
open on the last tab or Today, the scrolling ticker, and the "For you" ranking.
They are stored on the phone and applied before the page is drawn.

## Notifications

Each tab has its own colour (set with `color:` in `config.yaml`), and the app can
send a morning notification per tab in that colour. There is no server, so it
takes a one-time setup:

1. **Once:** add a repository secret `VAPID_PRIVATE_KEY` (Settings → Secrets and
   variables → Actions → Secrets). Make a key with `python -m news_digest.push`.
   The bell icon appears in the app after the next build.
2. **On each phone:** open the app (on iPhone: from the Home Screen icon, iOS 16.4+),
   tap the bell, pick the tabs and tap *Turn on*. Copy the code it shows.
3. Add the code as a new line to the repository **variable** `PUSH_SUBSCRIPTIONS`
   (Settings → Secrets and variables → Actions → Variables). One line per phone.

By default a phone only hears about **important** news in its tabs: a big
one-day price move, a rate decision or large yield move (`alert_bp:` in
`config.yaml`), or news Claude marks as important (for example a GTA 6 date or
an ECB decision), plus "The week in review" on Saturday. In the bell menu you
can pick "Every morning" instead. Notifications go out after the scheduled
morning run, and after a manual "Run workflow" so you can test them. Codes
made before this option existed use "important". If a phone's subscription expires, the
workflow log says so; turn notifications on again and replace that line.

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
  The repo is public, so keep names and contact details out of it, or put the
  whole text in a repository secret named `DIGEST_PROFILE`, which overrides it.
  Fill in the TODOs, especially where the diploma is from (EU/EEA or not).
  That determines which BIG procedure applies.
* **`sections`**: add or remove feeds and Google News queries. Queries support
  `OR`, `"exact phrase"`, `site:medischcontact.nl` and `-exclude`.
* **`watch_pages`**: official pages to monitor for changes.
* **`watchlist`**: Yahoo Finance symbols (Amsterdam stocks end in `.AS`).
* **`rates`**: interest-rate series from the [ECB Data Portal](https://data.ecb.europa.eu) (series key) or Yahoo Finance yield tickers.
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
