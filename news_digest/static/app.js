// The Daily Brief: saved stories and reading preferences (kept on this phone only),
// search over past editions, and tap-to-enlarge charts for the price and rate tiles.
(() => {
  const $ = id => document.getElementById(id);
  const load = (k, fallback) => { try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch (e) { return fallback; } };
  const store = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const norm = s => String(s).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  const label = sid => {
    const a = document.querySelector(`.tabs a[data-tab="${sid}"]`);
    return a ? a.firstChild.textContent.trim() : sid;
  };
  const shortDate = iso => { const d = new Date(iso + "T12:00:00"); return isNaN(d) ? "" : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" }); };

  // ------------------------------------------------------------------ saved stories
  let saved = load("brief-saved", []);

  function storyData(li) {
    const a = li.querySelector("a.hl");
    return { id: li.dataset.id, title: a.textContent.trim(), link: a.href, sec: li.dataset.sec,
             src: (li.querySelector(".src")?.firstChild?.textContent || "").trim(), date: li.dataset.date, at: Date.now() };
  }

  function syncStars() {
    const ids = new Set(saved.map(s => s.id));
    document.querySelectorAll("li[data-id] > .star").forEach(b => b.setAttribute("aria-pressed", ids.has(b.parentElement.dataset.id)));
    const badge = $("saved-count");
    badge.hidden = !saved.length;
    badge.textContent = saved.length;
  }

  function renderSaved() {
    $("saved-empty").hidden = saved.length > 0;
    $("saved-list").innerHTML = saved.map(s => `
      <li data-id="${esc(s.id)}" data-sec="${esc(s.sec)}" data-date="${esc(s.date || "")}">
        <button class="star" type="button" aria-label="Remove from saved" aria-pressed="true"></button>
        <div class="src" data-cat="${esc(s.sec)}"><span style="color:var(--cat)">${esc(label(s.sec))}</span> · ${esc(s.src)}</div>
        <a class="hl" href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.title)}</a>
        <div class="meta">${esc(shortDate(s.date))}</div>
      </li>`).join("");
  }

  const isSaved = id => saved.some(s => s.id === id);
  function toggleSave(data) {
    saved = isSaved(data.id) ? saved.filter(s => s.id !== data.id) : [data, ...saved].slice(0, 200);
    store("brief-saved", saved);
    syncStars();
  }

  document.addEventListener("click", e => {
    const star = e.target.closest("li[data-id] > .star");
    if (!star) return;
    e.preventDefault();
    e.stopPropagation();
    const li = star.parentElement;
    toggleSave(storyData(li));
    if (!li.closest("#saved-list")) renderSaved();
    else li.remove(), ($("saved-empty").hidden = saved.length > 0);
  }, true);

  // ------------------------------------------------------------------ reading preferences
  // Words and sources of the stories opened on this phone gain weight (fading ~3% a day);
  // each tab's best matches move to the top with a "For you" tag.
  const STOP = new Set(("the and for with from that this into over after about amid says said will what when where which while " +
    "their they them your have has had are was were been more than most just also only new news report reports update week " +
    "year years today could would should first last other some such there these those under while how why who its it's not").split(" "));
  const words = t => [...new Set((norm(t).match(/[a-z0-9][a-z0-9+&-]{2,}/g) || []).filter(w => !STOP.has(w)))];
  let prefs = load("brief-interest", { w: {}, s: {}, day: 0 });
  const today = Math.floor(Date.now() / 864e5);
  if (prefs.day && today > prefs.day) {
    const f = Math.pow(0.97, today - prefs.day);
    for (const m of [prefs.w, prefs.s]) for (const k in m) { m[k] *= f; if (m[k] < 0.05) delete m[k]; }
  }
  prefs.day = today;

  function learn(title, src) {
    words(title).forEach(w => prefs.w[w] = Math.min((prefs.w[w] || 0) + 1, 20));
    if (src) prefs.s[src] = Math.min((prefs.s[src] || 0) + 1, 20);
    const keys = Object.keys(prefs.w);
    if (keys.length > 600) keys.sort((x, y) => prefs.w[x] - prefs.w[y]).slice(0, keys.length - 600).forEach(k => delete prefs.w[k]);
    store("brief-interest", prefs);
  }

  function rank() {
    if (!Object.keys(prefs.w).length || load("brief-settings", {}).foryou === false) return;
    document.querySelectorAll(".panel:not([data-extra]) ul.stories:not(.older)").forEach(ul => {
      const lis = [...ul.children].filter(li => li.dataset.id);
      const scored = lis.map(li => {
        const title = li.querySelector("a.hl")?.textContent || "";
        const src = (li.querySelector(".src")?.firstChild?.textContent || "").trim().replace(/ \+\d+$/, "");
        const score = words(title).reduce((n, w) => n + (prefs.w[w] || 0), 0) + 0.5 * (prefs.s[src] || 0);
        return { li, score };
      }).filter(x => x.score >= 3).sort((a, b) => b.score - a.score).slice(0, 2);
      scored.reverse().forEach(({ li }) => {
        ul.prepend(li);
        const src = li.querySelector(".src");
        if (src && !src.querySelector(".foryou-tag")) src.insertAdjacentHTML("beforeend", '<span class="foryou-tag">For you</span>');
      });
    });
  }

  $("reset-interests")?.addEventListener("click", e => {
    e.preventDefault();
    prefs = { w: {}, s: {}, day: today };
    store("brief-interest", prefs);
    document.querySelectorAll(".foryou-tag").forEach(t => t.remove());
    e.target.textContent = "Reading preferences cleared";
  });

  // ------------------------------------------------------------------ search
  let index = null, timer = null;
  const box = $("search-box"), results = $("search-results"), status = $("search-status");

  async function loadIndex() {
    if (!index) {
      status.textContent = "Loading…";
      const res = await fetch("search.json", { cache: "no-cache" });
      let raw = await res.json();
      if (raw.locked) {  // site behind a passphrase: decrypt with this phone's key
        const b64 = x => Uint8Array.from(atob(x), c => c.charCodeAt(0));
        const key = await crypto.subtle.importKey("raw", b64(localStorage.getItem("brief-key")), "AES-GCM", false, ["decrypt"]);
        raw = JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: b64(raw.iv) }, key, b64(raw.ct))));
      }
      index = {
        items: raw.items.map(([date, sec, title, src, link]) => ({ date, sec, title, src, link, hay: norm(`${title} ${src} ${raw.sections[sec] || sec}`) })),
        briefs: raw.briefs.map(([date, sec, text]) => ({ date, sec, text, hay: norm(text) })),
        days: new Set(raw.items.map(i => i[0])).size,
      };
      status.textContent = `${index.items.length.toLocaleString()} stories from ${index.days} editions.`;
    }
    return index;
  }

  const mark = (text, terms) => {
    let out = esc(text);
    terms.forEach(t => { if (t.length > 1) out = out.replace(new RegExp(`(${t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"), "<mark>$1</mark>"); });
    return out;
  };

  async function search() {
    const q = box.value.trim();
    const terms = norm(q).split(/\s+/).filter(t => t.length > 1);
    if (!terms.length) { results.innerHTML = ""; if (index) status.textContent = `${index.items.length.toLocaleString()} stories from ${index.days} editions.`; return; }
    let idx;
    try { idx = await loadIndex(); } catch (e) { status.textContent = "Search needs a connection the first time."; return; }
    const hit = x => terms.every(t => x.hay.includes(t));
    const items = idx.items.filter(hit).slice(0, 80);
    const briefs = idx.briefs.filter(hit).slice(0, 6);
    status.textContent = items.length || briefs.length
      ? `${items.length === 80 ? "80+" : items.length} stories${briefs.length ? `, ${briefs.length} briefing${briefs.length > 1 ? "s" : ""}` : ""}`
      : "No matches.";
    const snippet = text => {
      const i = norm(text).indexOf(terms[0]);
      const start = Math.max(0, i - 90);
      return (start ? "…" : "") + text.slice(start, start + 240) + (start + 240 < text.length ? "…" : "");
    };
    results.innerHTML =
      briefs.map(b => `<li><div class="hit-meta" data-cat="${esc(b.sec)}"><span class="cat">${esc(label(b.sec))}</span> · Briefing · ${esc(shortDate(b.date))}</div>
        <div class="hit-text">${mark(snippet(b.text.replace(/^- /gm, "")), terms)}</div>
        <a class="meta" href="${esc(b.date)}.html#${esc(b.sec)}">Open that edition →</a></li>`).join("") +
      items.map(i => `<li><div class="hit-meta" data-cat="${esc(i.sec)}"><span class="cat">${esc(label(i.sec))}</span> · ${esc(i.src)} · ${esc(shortDate(i.date))}</div>
        <a class="hl" href="${esc(i.link)}" target="_blank" rel="noopener">${mark(i.title, terms)}</a></li>`).join("");
  }

  box?.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 150); });
  document.addEventListener("brief:tab", e => {
    if (e.detail === "search") { loadIndex().catch(() => {}); setTimeout(() => box.focus(), 50); }
    if (e.detail === "saved") renderSaved();
  });

  // ------------------------------------------------------------------ charts
  const charts = JSON.parse($("chart-data")?.textContent || "{}");
  const dlg = $("chart-dlg");
  const fmt = (v, kind) => kind === "pct" ? v.toFixed(2) + "%" : kind === "bp" ? Math.round(v * 100) + " bp"
    : v.toLocaleString("en-GB", { minimumFractionDigits: Math.abs(v) < 10 ? 4 : 2, maximumFractionDigits: Math.abs(v) < 10 ? 4 : 2 });
  const longDate = iso => new Date(iso + "T12:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  function change(c) {
    const p = c.points, first = p[0][1], last = p[p.length - 1][1];
    if (c.kind === "price") { const pct = (last / first - 1) * 100; return { up: pct >= 0, text: `${pct >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)}% over the period` }; }
    const bp = Math.round((last - first) * 100);
    return { up: bp >= 0, text: `${bp >= 0 ? "+" : "−"}${Math.abs(bp)} bp over the period` };
  }

  function draw(c) {
    const host = $("chart-box");
    const W = host.clientWidth || 600, H = host.clientHeight || 300, padR = 54, padB = 22, padT = 8;
    const vals = c.points.map(p => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const span = (hi - lo) || Math.abs(hi) * 0.01 || 1;
    lo -= span * 0.06; hi += span * 0.06;
    const x = i => (i / (c.points.length - 1)) * (W - padR);
    const y = v => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
    const color = change(c).up ? "var(--up)" : "var(--down)";
    const line = c.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
    let grid = "";
    for (let k = 0; k <= 4; k++) {
      const v = lo + (hi - lo) * k / 4, yy = y(v).toFixed(1);
      grid += `<line x1="0" x2="${W - padR}" y1="${yy}" y2="${yy}" stroke="var(--rule)" stroke-width="1"/>` +
              `<text x="${W - padR + 6}" y="${yy}" dy="4" font-size="11" fill="var(--muted)">${esc(fmt(v, c.kind))}</text>`;
    }
    const ticks = [0, Math.floor((c.points.length - 1) / 2), c.points.length - 1].map((i, n) =>
      `<text x="${x(i).toFixed(1)}" y="${H - 4}" font-size="11" fill="var(--muted)" text-anchor="${["start", "middle", "end"][n]}">${esc(new Date(c.points[i][0] + "T12:00:00").toLocaleDateString("en-GB", { month: "short", year: "2-digit" }))}</text>`).join("");
    host.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(c.name)} chart">${grid}${ticks}
      <path d="${line}L${x(c.points.length - 1)},${H - padB}L0,${H - padB}Z" fill="${color}" opacity=".08"/>
      <path d="${line}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round"/>
      <line id="cx" y1="${padT}" y2="${H - padB}" stroke="var(--muted)" stroke-dasharray="3 3" visibility="hidden"/>
      <circle id="cdot" r="4.5" fill="${color}" stroke="var(--card)" stroke-width="2" visibility="hidden"/></svg>`;
    const svg = host.firstChild, cx = svg.querySelector("#cx"), dot = svg.querySelector("#cdot");
    const summary = () => { const last = c.points[c.points.length - 1];
      $("chart-val").innerHTML = `<strong>${esc(fmt(last[1], c.kind))}</strong>${esc(change(c).text)}`; };
    const move = e => {
      const r = svg.getBoundingClientRect();
      const i = Math.max(0, Math.min(c.points.length - 1, Math.round(((e.clientX - r.left) / r.width) * W / (W - padR) * (c.points.length - 1))));
      const [d, v] = c.points[i];
      cx.setAttribute("x1", x(i)); cx.setAttribute("x2", x(i)); dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(v));
      cx.setAttribute("visibility", "visible"); dot.setAttribute("visibility", "visible");
      $("chart-val").innerHTML = `<strong>${esc(fmt(v, c.kind))}</strong>${esc(longDate(d))}`;
    };
    const leave = () => { cx.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); summary(); };
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerdown", move);
    svg.addEventListener("pointerleave", leave);
    svg.addEventListener("pointerup", e => { if (e.pointerType !== "mouse") setTimeout(leave, 1500); });
    summary();
  }

  let current = null;
  document.addEventListener("click", e => {
    const tile = e.target.closest(".tile[data-chart]");
    const c = tile && charts[tile.id];
    if (!c || !dlg || c.points.length < 2) return;  // no history yet: the tile keeps opening its source
    e.preventDefault();
    current = c;
    $("chart-title").textContent = c.name;
    $("chart-sub").textContent = c.sub;
    $("chart-range").textContent = `${longDate(c.points[0][0])} – ${longDate(c.points[c.points.length - 1][0])}`;
    const src = $("chart-src");
    src.hidden = !c.url;
    if (c.url) src.href = c.url;
    dlg.showModal();
    draw(c);
  });
  $("chart-close")?.addEventListener("click", () => dlg.close());
  dlg?.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });
  addEventListener("resize", () => { if (dlg?.open && current) draw(current); });

  // ------------------------------------------------------------------ in-app reader
  // Tapping a story (anywhere but its star) opens it here: picture, Claude's summary
  // of the article, why it matters, then a button to the full article at the source.
  const ART = JSON.parse($("articles")?.textContent || "{}");
  const reader = $("reader");
  let readingList = [], readingAt = -1, readerState = false;

  function articleFor(id) {
    if (ART[id]) return { id, ...ART[id] };
    const s = saved.find(x => x.id === id);  // saved from an older edition
    return s ? { id, t: s.title, l: s.link, s: s.src, d: s.date, sec: s.sec } : null;
  }

  function host(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; } }

  function articleMode(on) {
    reader.dataset.mode = on ? "article" : "topic";
    $("r-star").hidden = $("r-share").hidden = !on;
    $("r-rel-box").hidden = on;
    $("r-sum-k").textContent = on ? "Summary" : "The story";
    $("r-sum-foot").textContent = on ? "Written by Claude from the article. Check the source for details."
                                     : "From Claude's briefing. Tap an article below for its summary and source.";
    $("r-link").target = on ? "_blank" : "";
  }

  function showReader() {
    if (!reader.open) {
      reader.showModal();
      if (!readerState) { history.pushState({ reader: true }, "", location.href); readerState = true; }
    }
    reader.scrollTop = 0;
  }

  function openReader(id, list) {
    const a = articleFor(id);
    if (!a || !reader) return false;
    articleMode(true);
    readingList = list || [id];
    readingAt = readingList.indexOf(id);
    reader.dataset.cat = a.sec || "";
    $("r-sec").textContent = a.sec ? label(a.sec) : "";
    $("r-title").textContent = a.t;
    $("r-meta").textContent = [a.s + (a.n > 1 ? ` and ${a.n - 1} more` : ""), shortDate(a.d)].filter(Boolean).join(" · ");
    const img = $("r-img");
    img.hidden = true;
    img.onload = () => { img.hidden = false; };
    img.onerror = () => { img.hidden = true; };
    if (a.img) img.src = a.img; else img.removeAttribute("src");
    $("r-sum").textContent = a.sum || "";
    $("r-sum-box").hidden = !a.sum;
    $("r-note").textContent = a.note || "";
    $("r-note-box").hidden = !a.note;
    $("r-snip").textContent = a.snip || "";
    $("r-snip-box").hidden = !a.snip || !!a.sum;
    const src = host(a.l) && !host(a.l).endsWith("news.google.com") ? host(a.l) : a.s;
    $("r-link").href = a.l;
    $("r-link").textContent = `Read the full article${src ? " at " + src : ""} ↗`;
    $("r-star").setAttribute("aria-pressed", isSaved(id));
    const nextId = readingList[readingAt + 1], next = nextId && articleFor(nextId);
    $("r-next").hidden = !next;
    if (next) $("r-next").innerHTML = `Next story<span>${esc(next.t)}</span>`;
    showReader();
    learn(a.t, a.s);
    return true;
  }

  // Tapping a summary point (a briefing bullet, an "In one minute" line or a Today card)
  // opens it with the articles it is based on: Claude's own references when the edition
  // has them, otherwise the articles of that tab that share the most words with it.
  let topics = [], topicAt = -1;
  const overlap = (a, b) => { const set = new Set(words(a)); return words(b).filter(w => set.has(w)).length; };

  function related(sec, text, refs) {
    const own = refs && refs.filter(id => ART[id]);
    if (own && own.length) return { ids: own, exact: true };
    const pool = Object.entries(ART).filter(([id, a]) => id !== "_refs" && a.sec === sec);
    const scored = pool.map(([id, a]) => ({ id, score: overlap(text, a.t) + 0.6 * overlap(text, a.sum || "") + 0.6 * overlap(text, a.note || "") }))
      .filter(x => x.score >= 2.4).sort((x, y) => y.score - x.score).slice(0, 5).map(x => x.id);
    if (scored.length) return { ids: scored, exact: false };
    // Nothing shares enough words (e.g. an English point about Dutch articles): show the tab's top stories.
    return { ids: pool.filter(([, a]) => a.note || a.sum).slice(0, 4).map(([id]) => id), exact: false, fallback: true };
  }

  function bulletsOf(sec) {
    const lis = [...document.querySelectorAll(`#tab-${sec} > .brief > ul > li`)];
    const refs = (ART._refs || {})[sec] || [];
    return lis.map((li, i) => ({ sec, li, text: li.textContent.trim(), lead: li.querySelector("strong")?.textContent.trim() || "", refs: refs[i] || [] }));
  }

  function openTopic(list, at) {
    const t = list[at];
    if (!t || !reader) return false;
    topics = list; topicAt = at;
    articleMode(false);
    reader.dataset.cat = t.sec;
    $("r-sec").textContent = label(t.sec);
    let title = t.lead.replace(/[.:]$/, ""), body = t.text;
    if (title) body = t.text.slice(t.text.indexOf(t.lead) + t.lead.length).replace(/^[\s.:–—-]+/, "").replace(/ ›$/, "");
    else { const m = t.text.match(/^(.+?[.!?])\s+(.*)$/s); title = m ? m[1] : t.text; body = m ? m[2] : ""; }
    $("r-title").textContent = title;
    $("r-meta").textContent = t.where || `From the ${label(t.sec)} briefing`;
    $("r-img").hidden = true;
    $("r-sum").textContent = body;
    $("r-sum-box").hidden = !body;
    $("r-note-box").hidden = true;
    $("r-snip-box").hidden = true;
    const rel = related(t.sec, t.text, t.refs), ids = rel.ids;
    $("r-rel-box").querySelector(".kicker").textContent = rel.exact ? "The articles behind it"
      : rel.fallback ? `Top stories in ${label(t.sec)}` : "Related articles";
    $("r-rel").innerHTML = ids.map(id => { const a = ART[id];
      return `<li data-rel="${esc(id)}"><div class="src">${esc(a.s || "")}</div><a class="hl" href="${esc(a.l)}">${esc(a.t)}</a>
        <div class="meta">${esc(shortDate(a.d))}${a.sum ? " · summary available" : ""}</div></li>`; }).join("");
    $("r-rel-box").hidden = !ids.length;
    $("r-link").href = `#${t.sec}`;
    $("r-link").textContent = `Open the ${label(t.sec)} tab`;
    const next = list[at + 1];
    $("r-next").hidden = !next;
    if (next) $("r-next").innerHTML = `Next point<span>${esc((next.lead || next.text).replace(/ ›$/, "").slice(0, 120))}</span>`;
    showReader();
    return true;
  }

  document.addEventListener("click", e => {
    if (e.defaultPrevented || e.target.closest("dialog, a, button")) return;
    const bullet = e.target.closest(".panel > .brief > ul > li");
    const minute = !bullet && e.target.closest(".minute li[data-cat]");
    const stand = !bullet && !minute && e.target.closest(".card .standfirst");
    if (bullet) {
      const sec = bullet.closest(".panel").dataset.panel;
      const list = sec === "week" ? [...bullet.parentElement.children].map(li => ({ sec: li.closest("[data-cat]")?.dataset.cat, li, text: li.textContent.trim(),
        lead: li.querySelector("strong")?.textContent.trim() || "", refs: [], where: "From the week in review" })) : bulletsOf(sec);
      const at = list.findIndex(t => t.li === bullet);
      if (at >= 0 && openTopic(list, at)) e.preventDefault();
    } else if (minute) {
      const items = [...minute.parentElement.querySelectorAll(":scope > li[data-cat]")].map(li => {
        const sec = li.dataset.cat, text = li.querySelector("p")?.textContent.trim() || li.textContent.trim();
        const best = bulletsOf(sec).map(b => ({ b, n: overlap(text, b.text) })).sort((x, y) => y.n - x.n)[0];
        return { sec, li, text, lead: "", refs: best && best.n >= 2 ? best.b.refs : [], where: "In one minute" };
      });
      openTopic(items, items.findIndex(t => t.li === minute));
    } else if (stand) {
      const sec = stand.closest(".card").dataset.cat, list = bulletsOf(sec);
      if (list.length) openTopic(list, 0);
    }
  });

  function closeReader(fromHistory) {
    if (!reader?.open) return;
    reader.close();
    if (readerState && !fromHistory) { readerState = false; history.back(); }
    readerState = false;
  }

  document.addEventListener("click", e => {
    if (e.defaultPrevented || e.target.closest("dialog, .star")) return;
    const link = e.target.closest("a[data-article]");
    const li = !link && e.target.closest("li[data-id]");
    const id = link ? link.dataset.article : li && li.dataset.id;
    if (!id) return;
    const list = li ? [...li.parentElement.querySelectorAll(":scope > li[data-id]")].map(x => x.dataset.id) : [id];
    if (openReader(id, list)) e.preventDefault();
  });

  $("r-back")?.addEventListener("click", () => closeReader());
  reader?.addEventListener("cancel", e => { e.preventDefault(); closeReader(); });
  addEventListener("popstate", () => closeReader(true));
  $("r-next")?.addEventListener("click", () => reader.dataset.mode === "topic"
    ? openTopic(topics, topicAt + 1) : openReader(readingList[readingAt + 1], readingList));
  $("r-rel")?.addEventListener("click", e => {
    const li = e.target.closest("li[data-rel]");
    if (!li) return;
    e.preventDefault();
    openReader(li.dataset.rel, [...$("r-rel").children].map(x => x.dataset.rel));
  });
  $("r-link")?.addEventListener("click", e => {
    if (reader.dataset.mode !== "topic") return;
    e.preventDefault();
    const sec = topics[topicAt]?.sec;
    closeReader();
    if (sec) setTimeout(() => { location.hash = sec; }, 50);
  });
  $("r-star")?.addEventListener("click", () => {
    const a = articleFor(readingList[readingAt]);
    if (!a) return;
    toggleSave({ id: a.id, title: a.t, link: a.l, sec: a.sec, src: a.s, date: a.d, at: Date.now() });
    $("r-star").setAttribute("aria-pressed", isSaved(a.id));
    renderSaved();
  });
  $("r-share")?.addEventListener("click", async () => {
    const a = articleFor(readingList[readingAt]);
    if (!a) return;
    try {
      if (navigator.share) await navigator.share({ title: a.t, text: a.sum || a.t, url: a.l });
      else { await navigator.clipboard.writeText(a.l); $("r-share").textContent = "Link copied"; setTimeout(() => $("r-share").textContent = "Share", 1500); }
    } catch (err) {}
  });

  // ------------------------------------------------------------------ listen
  // Reads the brief aloud with the phone's own voice (no data leaves the phone).
  let speaking = null;
  function stopSpeaking() {
    speechSynthesis.cancel();
    document.querySelectorAll(".listen.playing").forEach(b => { b.classList.remove("playing"); b.textContent = "▶ Listen"; });
    document.querySelectorAll(".speaking").forEach(el => el.classList.remove("speaking"));
    speaking = null;
  }
  document.addEventListener("click", e => {
    const btn = e.target.closest(".listen");
    if (!btn) return;
    if (!("speechSynthesis" in window)) { btn.textContent = "Not supported"; return; }
    const same = speaking === btn;
    stopSpeaking();
    if (same) return;
    const box = document.querySelector(btn.dataset.listen);
    const parts = box ? [...box.querySelectorAll("li, p")].filter(el => el.textContent.trim()) : [];
    if (!parts.length) return;
    const voices = speechSynthesis.getVoices();
    const voice = voices.find(v => /en-GB/i.test(v.lang)) || voices.find(v => /^en/i.test(v.lang));
    speaking = btn;
    btn.classList.add("playing");
    btn.textContent = "■ Stop";
    parts.forEach((el, i) => {
      const u = new SpeechSynthesisUtterance(el.textContent.replace(/\s+/g, " ").trim());
      if (voice) u.voice = voice;
      u.rate = 1.02;
      u.onstart = () => { document.querySelectorAll(".speaking").forEach(x => x.classList.remove("speaking")); el.classList.add("speaking"); };
      if (i === parts.length - 1) u.onend = () => { if (speaking === btn) stopSpeaking(); };
      speechSynthesis.speak(u);
    });
  });
  document.addEventListener("brief:tab", stopSpeaking);

  // Calendar: subscribe (webcal) so new dates arrive by themselves.
  const cal = $("cal-link");
  if (cal) cal.href = new URL("calendar.ics", location.href).href.replace(/^https?:/, "webcal:");

  // ------------------------------------------------------------------ settings
  // Theme and text size apply at once (and before drawing, see _head.html.j2);
  // tabs, start page, ticker and "For you" apply when Settings closes.
  const sdlg = $("settings");
  const S = () => load("brief-settings", {});
  const root = document.documentElement;

  function applyLook(set) {
    if (set.theme === "light" || set.theme === "dark") { root.dataset.theme = set.theme; root.style.colorScheme = set.theme; }
    else { delete root.dataset.theme; root.style.colorScheme = ""; }
    document.querySelectorAll('meta[name="theme-color"]').forEach((m, i) =>
      m.content = set.theme === "dark" ? "#111112" : set.theme === "light" ? "#fff1e5" : (i ? "#111112" : "#fff1e5"));
    if (set.size && set.size !== 100) root.style.setProperty("--fs", set.size + "%"); else root.style.removeProperty("--fs");
  }

  function fill() {
    const set = S();
    const pick = (name, value) => sdlg.querySelectorAll(`input[name=${name}]`).forEach(r => r.checked = r.value === String(value));
    pick("set-theme", set.theme || "system");
    pick("set-size", set.size || 100);
    pick("set-start", set.start || "last");
    $("set-ticker").checked = set.ticker !== false;
    $("set-foryou").checked = set.foryou !== false;
    sdlg.querySelectorAll("#set-tabs input").forEach(b => b.checked = !(set.hidden || []).includes(b.value));
  }

  function read() {
    const val = name => sdlg.querySelector(`input[name=${name}]:checked`)?.value;
    return {
      theme: val("set-theme"), size: Number(val("set-size")) || 100, start: val("set-start"),
      ticker: $("set-ticker").checked, foryou: $("set-foryou").checked,
      hidden: [...sdlg.querySelectorAll("#set-tabs input")].filter(b => !b.checked).map(b => b.value),
    };
  }

  if (sdlg) {
    let before = "";
    $("settings-btn").addEventListener("click", () => { fill(); before = JSON.stringify(S()); sdlg.showModal(); });
    sdlg.addEventListener("change", () => { const set = read(); store("brief-settings", set); applyLook(set); });
    const close = () => {
      sdlg.close();
      const now = S(), was = JSON.parse(before || "{}");
      // Tab list, start page, ticker and ranking are set up at load time: reload if they changed.
      if (["hidden", "start", "ticker", "foryou"].some(k => JSON.stringify(now[k]) !== JSON.stringify(was[k]))) location.reload();
    };
    $("settings-done").addEventListener("click", close);
    sdlg.addEventListener("cancel", e => { e.preventDefault(); close(); });
    sdlg.addEventListener("click", e => { if (e.target === sdlg) close(); });
    $("settings-notify")?.addEventListener("click", () => { sdlg.close(); $("bell")?.click(); });
    const lockBtn = $("settings-lock");
    if (lockBtn) {
      let hasKey = false;
      try { hasKey = !!localStorage.getItem("brief-key"); } catch (e) {}
      lockBtn.hidden = !hasKey;
      lockBtn.addEventListener("click", e => {
        e.preventDefault();
        try { localStorage.removeItem("brief-key"); } catch (err) {}
        location.reload();
      });
    }
    $("settings-reset").addEventListener("click", e => {
      e.preventDefault();
      try { localStorage.removeItem("brief-settings"); } catch (err) {}
      applyLook({});
      fill();
    });
  }

  syncStars();
  renderSaved();
  rank();
})();
