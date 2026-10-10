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

  document.addEventListener("click", e => {
    const star = e.target.closest("li[data-id] > .star");
    if (!star) return;
    e.preventDefault();
    const li = star.parentElement, id = li.dataset.id;
    saved = saved.some(s => s.id === id) ? saved.filter(s => s.id !== id) : [storyData(li), ...saved].slice(0, 200);
    store("brief-saved", saved);
    syncStars();
    if (!li.closest("#saved-list")) renderSaved();
    else li.remove(), ($("saved-empty").hidden = saved.length > 0);
  });

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

  document.addEventListener("click", e => {
    const a = e.target.closest("li[data-id] a.hl");
    if (!a) return;
    const li = a.closest("li");
    words(a.textContent).forEach(w => prefs.w[w] = Math.min((prefs.w[w] || 0) + 1, 20));
    const src = (li.querySelector(".src")?.firstChild?.textContent || "").trim().replace(/ \+\d+$/, "");
    if (src) prefs.s[src] = Math.min((prefs.s[src] || 0) + 1, 20);
    const keys = Object.keys(prefs.w);
    if (keys.length > 600) keys.sort((x, y) => prefs.w[x] - prefs.w[y]).slice(0, keys.length - 600).forEach(k => delete prefs.w[k]);
    store("brief-interest", prefs);
  }, true);

  function rank() {
    if (!Object.keys(prefs.w).length) return;
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
      const raw = await res.json();
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

  syncStars();
  renderSaved();
  rank();
})();
