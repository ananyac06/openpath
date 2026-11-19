"""Local-only read-only web server for inspecting research results, live opportunities, and the 1,000+ verified organizations directory."""

from __future__ import annotations

import html
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from openpath.config import Config
from openpath.db.connection import DatabaseManager
from openpath.db.migrations import apply_migrations
from openpath.db.repository import Repository
from openpath.models.entities import Opportunity

logger = logging.getLogger(__name__)

INTERN_REGEX = re.compile(
    r"\b(intern|internship|summer|winter|trainee|apprentice|co-op)\b", re.IGNORECASE
)
ENTRY_REGEX = re.compile(
    r"\b(junior|entry|associate|graduate|fresher|l1|level 1|beginner|early career)\b",
    re.IGNORECASE,
)

COMPANY_METADATA: dict[str, dict[str, str]] = {
    "Cloudflare": {
        "ticker": "NYSE: NET • S&P 500 Leader",
        "category": "us_sp500",
        "avatar": "CF",
        "color": "#f38020",
    },
    "MongoDB": {
        "ticker": "NASDAQ: MDB • Global Cloud Database Leader",
        "category": "us_sp500",
        "avatar": "MD",
        "color": "#00ed64",
    },
    "Elastic": {
        "ticker": "NYSE: ESTC • Search & AI Observability Leader",
        "category": "us_sp500",
        "avatar": "EL",
        "color": "#005571",
    },
    "Canonical": {
        "ticker": "Ubuntu Linux & Open Source Enterprise",
        "category": "open_source",
        "avatar": "CA",
        "color": "#e95420",
    },
    "GitLab": {
        "ticker": "NASDAQ: GTLB • The DevSecOps Platform",
        "category": "us_sp500",
        "avatar": "GL",
        "color": "#fc6d26",
    },
    "Mozilla": {
        "ticker": "Firefox, Rust & Open Web Foundation",
        "category": "open_source",
        "avatar": "MZ",
        "color": "#ff7139",
    },
    "Supabase": {
        "ticker": "Y-Combinator Open Source Cloud Unicorn",
        "category": "tech_unicorn",
        "avatar": "SB",
        "color": "#3ecf8e",
    },
    "Meesho": {
        "ticker": "Top Indian E-Commerce Unicorn (Bengaluru)",
        "category": "tech_unicorn",
        "avatar": "ME",
        "color": "#f43397",
    },
    "CRED": {
        "ticker": "Top Indian Fintech Unicorn (Bengaluru)",
        "category": "tech_unicorn",
        "avatar": "CR",
        "color": "#212529",
    },
    "Groww": {
        "ticker": "BSE/NSE Registered Indian Wealthtech Leader",
        "category": "indian_listed",
        "avatar": "GW",
        "color": "#00d09c",
    },
    "PostHog": {
        "ticker": "Open Source Product Analytics Platform",
        "category": "tech_unicorn",
        "avatar": "PH",
        "color": "#ffd000",
    },
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OpenPath — Research Viewer & Verified Directory</title>
<style>
  :root {
    --bg: #0a0d14;
    --bg-2: #0f1420;
    --fg: #e6edf3;
    --fg-dim: #98a3b2;
    --card: #141924;
    --card-hover: #1a2130;
    --border: #2a3346;
    --accent: #3f8cff;
    --accent-glow: rgba(63,140,255,0.16);
    --green: #26c67f;
    --red: #f05252;
    --amber: #e2b93b;
    --purple: #9e7aff;
    --blue: #5ac8fa;
    --orange: #ff9f0a;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    font-family: "Inter", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }
  header {
    position: sticky; top: 0; z-index: 50;
    backdrop-filter: blur(8px);
    background: rgba(10,13,20,0.72);
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; gap: 24px; padding: 12px 28px;
  }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--fg); font-size: 20px; font-weight: 700; text-decoration: none; }
  .brand span { letter-spacing: -0.03em; }
  nav { display: flex; gap: 6px; flex-wrap: wrap; }
  nav a { color: var(--fg-dim); padding: 8px 16px; border-radius: 22px; text-decoration: none; font-size: 14px; }
  nav a:hover { color: var(--fg); background: var(--card-hover); }
  nav a.active { color: var(--accent); background: var(--accent-glow); font-weight: 600; }
  main { padding: 36px 28px; max-width: 1400px; margin: 0 auto; }
  .hero { text-align: center; padding: 20px 8px 28px; border-bottom: 1px dashed var(--border); margin-bottom: 28px; }
  .hero h1 { font-size: clamp(26px, 4.2vw, 44px); font-weight: 800; margin: 0; letter-spacing: -0.02em; line-height: 1.1; }
  .hero p { color: var(--fg-dim); max-width: 640px; margin: 12px auto 0; font-size: 16px; }
  section { margin-bottom: 40px; }
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .stat {
    display: flex; flex-direction: column; padding: 18px 20px;
    background: var(--card);
    border: 1px solid var(--border); border-radius: 12px;
  }
  .stat-value { font-size: 30px; font-weight: 800; margin-bottom: 4px; }
  .stat-label { color: var(--fg-dim); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
  /* Opportunity cards carry a wide roles table: give them two columns so the
     table fits without horizontal scrolling at desktop widths. */
  #oppsGrid { grid-template-columns: repeat(auto-fill, minmax(540px, 1fr)); }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px 20px; transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s; }
  .card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.35); }
  .card-title { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .card-title h3 { font-size: 17px; margin: 0; }
  .avatar { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; color: #fff; flex-shrink: 0; }
  .avatar.green { background: #238636; } .avatar.blue { background: #1f6feb; }
  .avatar.purple { background: #8957e5; } .avatar.red { background: #da3633; }
  .avatar.amber { background: #d29922; } .avatar.cyan { background: #00d09c; }
  .avatar.orange { background: #f38020; }
  .card-footer { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
  .btn {
    display: inline-flex; align-items: center; gap: 8px; padding: 10px 18px;
    border-radius: 30px; text-decoration: none; font-size: 13px; font-weight: 600;
    border: 1px solid transparent; cursor: pointer; transition: filter 0.18s, box-shadow 0.18s, background 0.18s; white-space: nowrap;
  }
  .btn-primary { background: var(--accent); color: #fff; box-shadow: 0 0 0 0 var(--accent); }
  .btn-primary:hover { filter: brightness(1.1); box-shadow: 0 4px 14px var(--accent-glow); }
  .btn-ghost { color: var(--fg); border-color: var(--border); background: rgba(255,255,255,0.02); }
  .btn-ghost:hover { background: var(--card); border-color: var(--fg); }
  .btn-apply { background: #1c2736; border-color: var(--border); color: var(--fg-dim); font-size: 12px; }
  .btn-apply:hover { color: var(--fg); background: var(--card); border-color: var(--accent); }
  .search { display: flex; gap: 8px; margin-bottom: 22px; }
  .search input { flex: 1; padding: 11px 16px; border-radius: 30px; background: var(--card); border: 1px solid var(--border); color: var(--fg); font-size: 14px; }
  .search input:focus { outline: 1px solid var(--accent); }
  table.opportunities { width: 100%; border-collapse: separate; border-spacing: 0; }
  table.opportunities th, table.opportunities td { padding: 12px 14px; text-align: left; }
  table.opportunities thead th { color: var(--fg-dim); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; background: var(--bg-2); border-bottom: 1px solid var(--border); }
  table.opportunities tbody tr { border-bottom: 1px solid rgba(42,51,70,0.5); }
  table.opportunities tbody tr:hover { background: rgba(63,140,255,0.06); }
  .badge { display: inline-block; padding: 3px 9px; border-radius: 12px; font-size: 11px; font-weight: 600; border: 1px solid transparent; background: rgba(255,255,255,0.06); }
  .badge.ver {}
  .badge.int { background: rgba(35,134,54,0.16); color: var(--green); border-color: var(--green); }
  .badge.lead { background: rgba(210,153,34,0.16); color: var(--amber); border-color: var(--amber); }
  .badge.remote { background: rgba(188,140,255,0.14); color: var(--purple); border-color: var(--purple); }
  .badge.hybrid { background: rgba(5,202,240,0.14); color: var(--blue); border-color: var(--blue); }
  .badge.onsite { background: rgba(247,129,57,0.14); color: var(--orange); border-color: var(--orange); }
  .badge.verified { background: rgba(63,140,255,0.14); color: var(--accent); border-color: var(--accent); }
  a.title { font-size: 14px; color: var(--fg); text-decoration: none; font-weight: 600; }
  a.title:hover { color: var(--accent); text-decoration: underline; }
  .muted { color: var(--fg-dim); font-size: 13px; }
  .inline-table td { border-bottom: 1px solid var(--border); }
  footer { display: flex; gap: 16px; align-items: center; padding: 40px 28px 32px; border-top: 1px solid var(--border); font-size: 13px; color: var(--fg-dim); flex-wrap: wrap; justify-content: space-between; }
  .chip { padding: 3px 9px; border-radius: 12px; font-size: 11px; background: rgba(255,255,255,0.06); }
  input, button { font: inherit; }
  .has-filters .card { opacity: 0.45; }
  .card.hidden { display: none; }
  .empty { text-align: center; padding: 40px; color: var(--fg-dim); }
  .tabs { display: flex; gap: 6px; margin-bottom: 24px; flex-wrap: wrap; }
  .tabs button { padding: 10px 18px; border-radius: 30px; border: 1px solid var(--border); background: rgba(255,255,255,0.03); color: var(--fg-dim); cursor: pointer; }
  .tabs button.active { background: var(--accent-glow); color: var(--accent); font-weight: 600; }

  /* Interactive JS behavior is also exposed for non-JS clients via the
     same semantics: tab state via anchors, filter via classes. */
  .stat-card.stat-card-active, .tabs button.active, nav a.active {
    border-color: var(--accent);
    background: var(--accent-glow);
    color: var(--accent);
    font-weight: 600;
  }
  .company-card.card-hidden, tr.opp-row.hidden { display: none; }
  #emptyOpps { display: block; text-align: center; color: var(--fg-dim); }
  #emptyOpps .btn { display: inline-flex; }
  .opps-filter-bar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  #directoryGrid .company-card .avatar { width: 40px; height: 40px; border-radius: 12px; font-size: 16px; }
  /* Grid children must be allowed to shrink below the table's min-width,
     otherwise the cards grow wider than the columns and the page scrolls. */
  .card, .company-card { min-width: 0; }
  #oppsGrid .company-card .company-summary { display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; }
  #oppsGrid .company-card .company-header-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
  #oppsGrid .company-card .company-title-block { font-size: 16px; min-width: 0; }
  #oppsGrid .company-card .company-title {
    margin: 0; font-size: 16px; line-height: 1.25;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  #oppsGrid .company-card .company-ticker {
    display: block; margin-top: 3px; font-size: 11px; font-weight: 500;
    color: var(--fg-dim); letter-spacing: 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  #oppsGrid .company-card .badge-count { flex-shrink: 0; font-size: 11px; }
  #oppsGrid .company-card .company-badges { display: flex; gap: 6px; flex-wrap: wrap; flex-shrink: 0; max-width: 45%; justify-content: flex-end; }
  #oppsGrid .company-card .company-badges .badge { font-size: 10px; white-space: nowrap; }
  #oppsGrid .company-card table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 13px; }
  #oppsGrid .company-card thead th { padding: 8px 12px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--fg-dim); border-bottom: 1px solid var(--border); background: var(--bg-2); }
  #oppsGrid .company-card tbody tr:hover { background: rgba(63,140,255,0.05); }
  #oppsGrid .company-card tbody tr:last-child td { border-bottom: 0; }
  .role-cell { max-width: 260px; overflow: hidden; text-overflow: ellipsis; }

  /* Tables scroll inside their card instead of pushing the page wide. */
  .company-roles { overflow-x: auto; }
  .opportunities-table, table.opportunities { min-width: 640px; }

  @media (max-width: 900px) {
    /* Two columns on tablet and phone; the fifth stat spans the full row
       so no single card is orphaned. */
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stat:last-child { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 14px; }
    .stat:last-child .stat-value { margin-bottom: 0; }
    .grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
    #oppsGrid { grid-template-columns: 1fr; }
  }

  @media (max-width: 620px) {
    /* Header becomes two rows: wordmark, then a full-width tab bar. */
    header { flex-direction: column; align-items: stretch; gap: 8px; padding: 10px 16px; }
    .brand { font-size: 18px; }
    nav { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
    nav a { padding: 8px 10px; font-size: 13px; text-align: center; }
    main { padding: 20px 16px; }
    .hero { padding: 8px 0 20px; margin-bottom: 20px; }
    .hero p { font-size: 15px; }
    .stats { gap: 10px; margin-bottom: 20px; }
    .stat { padding: 14px 16px; }
    .stat-value { font-size: 26px; }
    .stat-label { font-size: 11px; letter-spacing: 0.04em; }
    .search { flex-direction: column; align-items: stretch; }
    .search input { min-width: 0; width: 100%; }
    .search .chip { align-self: flex-start; }
    .tabs { gap: 6px; margin-bottom: 18px; }
    .tabs button { padding: 8px 12px; font-size: 13px; }
    .grid { grid-template-columns: 1fr; }
    section { margin-bottom: 28px; }
    footer { padding: 28px 16px 24px; }
    /* Hide the two least useful columns in the roles table on phones. */
    table.opportunities th:nth-child(4), table.opportunities td:nth-child(4),
    table.opportunities th:nth-child(5), table.opportunities td:nth-child(5) { display: none; }
    .company-summary { flex-wrap: wrap; }
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
  }
</style>
</head>
<body>
<header>
  <a class="brand" href="#"><span>OpenPath</span> Research Viewer</a>
  <nav>
    <a class="active" href="#opportunities" id="btnViewOpportunities">Live Roles</a>
    <a href="#directory" id="btnViewDirectory">Verified Directory</a>
  </nav>
</header>
<main>
  <section class="hero">
    <h1>OpenPath Research Viewer &amp; Verified Directory</h1>
    <p>Live ingested opportunity roles — internships and entry-level drives — plus the directory of verified corporate career portals.</p>
  </section>
  <section>
    <div class="stats">
      <div class="stat"><span class="stat-value">{total_verified_orgs}</span><span class="stat-label">Verified Organizations</span></div>
      <div class="stat"><span class="stat-value">{total_opportunities}</span><span class="stat-label">Live Ingested Roles</span></div>
      <div class="stat"><span class="stat-value">{internship_count}</span><span class="stat-label">Internships &amp; Apprenticeships</span></div>
      <div class="stat"><span class="stat-value">{entry_count}</span><span class="stat-label">Zero-Exp &amp; Entry-Level</span></div>
      <div class="stat"><span class="stat-value">{remote_count}</span><span class="stat-label">Remote &amp; Hybrid</span></div>
    </div>
    <div class="search">
      <input type="text" id="dirSearchInput" placeholder="Search 1,120+ verified organizations by name, ticker, or country…" autocomplete="off">
      <span id="dirResultCount" class="chip">{total_verified_orgs} organizations</span>
    </div>
    <div class="tabs">
      <button type="button" class="active" id="tabAll" onclick="setDirFilter('all', this)">All</button>
      <button type="button" id="tabTech" onclick="setDirFilter('tech_unicorn', this)">Tech Unicorns &amp; Startups</button>
      <button type="button" id="tabIndian" onclick="setDirFilter('indian_tech', this)">Indian Tech &amp; Unicorns</button>
      <button type="button" id="tabOss" onclick="setDirFilter('open_source', this)">Open Source</button>
      <button type="button" id="tabRes" onclick="setDirFilter('research_institute', this)">Research Institutes</button>
    </div>
    <div id="sectionOpportunities">
      <div class="search">
        <input type="text" id="roleSearchInput" placeholder="Search live roles by title, company, location, or class…" autocomplete="off">
      </div>
      <div class="tabs" id="oppTabs">
        <button type="button" class="active" id="tabAllOpps">All Live Roles</button>
        <button type="button" id="tabInternship">Internships</button>
        <button type="button" id="tabEntry">Entry-Level</button>
        <button type="button" id="tabRemote">Remote &amp; Hybrid</button>
        <button type="button" id="tabUsSp500">S&amp;P 500</button>
        <button type="button" id="tabIndianTech">Indian Tech</button>
      </div>
      <section class="grid" id="oppsGrid">{cards}</section>
    </div>
    <div id="sectionDirectory" style="display: none;">
      <div class="grid" id="directoryGrid">{directory_cards}</div>
    </div>
  </section>
</main>
<footer>
  <div>OpenPath — Local-only research engine · 127.0.0.1 Local Only · {verified_count} verified roles · {sp500_orgs_count} S&amp;P 500 · {indian_orgs_count} Indian-listed · {unicorn_orgs_count} unicorns · {oss_orgs_count} open-source · {res_orgs_count} research institutes</div>
  <div><a class="btn btn-ghost" href="/">Refresh</a></div>
</footer>

<script>
(function () {
  "use strict";
  var state = { view: "directory", dirFilter: "all", oppFilter: "all", dirSearch: "", roleSearch: "" };
  var dirGrid = document.getElementById("directoryGrid");
  var oppsGrid = document.getElementById("oppsGrid");
  var sectionOpps = document.getElementById("sectionOpportunities");
  var sectionDir = document.getElementById("sectionDirectory");
  var roleCountBadge = document.getElementById("totalOppsCount");

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function setView(view, filterVal) {
    state.view = view;
    if (view === "directory") {
      if (filterVal) { state.dirFilter = filterVal; }
    } else {
      if (filterVal) { state.oppFilter = filterVal; }
    }
    document.querySelectorAll(".stat-card").forEach(function (card) {
      var isDir = card.getAttribute("data-view") === "directory";
      var active = state.view === card.getAttribute("data-view");
      card.classList.toggle("stat-card-active", active);
    });
    var oppTab = document.querySelector('nav a[href="#opportunities"]');
    var dirTab = document.querySelector('nav a[href="#directory"]');
    if (oppTab) { oppTab.classList.toggle("active", state.view === "opportunities"); }
    if (dirTab) { dirTab.classList.toggle("active", state.view === "directory"); }
    sectionOpps.style.display = state.view === "opportunities" ? "" : "none";
    sectionDir.style.display = state.view === "directory" ? "" : "none";
    applyDirFilters();
    applyOppFilters();
    updateCounts();
  }

  function visibleCards(root, filterFn, countBadge) {
    var cards = Array.prototype.slice.call(root.querySelectorAll(":scope > .company-card, :scope > .org-card"));
    var visible = 0;
    cards.forEach(function (card) {
      var hide = !filterFn(card);
      card.classList.toggle("card-hidden", hide);
      if (!hide) { visible++; }
    });
    if (countBadge) { countBadge.textContent = visible + " visible"; }
    return visible;
  }

  function dirMatchesFilter(card, filter) {
    if (filter === "all") { return true; }
    return (card.getAttribute("data-category") === filter) ||
           (filter === "indian_tech" && card.getAttribute("data-category") === "indian_listed");
  }

  function dirMatchesSearch(card, q) {
    if (!q) { return true; }
    var fields = [card.getAttribute("data-name"), card.getAttribute("data-ticker"),
                  card.getAttribute("data-country"), card.textContent || ""];
    return fields.some(function (f) { return f && f.toLowerCase().indexOf(q) >= 0; });
  }

  // Row-level filters: each <tr> carries data-role-type and data-work-mode;
  // company category lives on the enclosing <details> card.
  function rowMatchesFilter(row, filter) {
    if (filter === "all") { return true; }
    if (filter === "remote") {
      var mode = row.getAttribute("data-work-mode");
      return mode === "remote" || mode === "hybrid";
    }
    if (filter === "us_sp500" || filter === "indian_tech") {
      var card = row.closest(".company-card");
      var cat = card ? card.getAttribute("data-category") : "";
      return filter === "us_sp500" ? cat === "us_sp500"
        : (cat === "indian_tech" || cat === "indian_listed");
    }
    return row.getAttribute("data-role-type") === filter;
  }

  function rowMatchesSearch(row, q) {
    if (!q) { return true; }
    return (row.textContent || "").toLowerCase().indexOf(q) >= 0;
  }

  function applyDirFilters() {
    visibleCards(dirGrid, function (c) {
      return dirMatchesFilter(c, state.dirFilter) && dirMatchesSearch(c, state.dirSearch);
    });
  }

  function applyOppFilters() {
    var roles = document.querySelectorAll("tr.opp-row");
    var hasMatches = false;
    roles.forEach(function (row) {
      var card = row.closest("details");
      if (!card) { return; }
      var matched = rowMatchesFilter(row, state.oppFilter) && rowMatchesSearch(row, state.roleSearch);
      row.classList.toggle("hidden", !matched);
      if (matched) { hasMatches = true; }
    });
    // hide company cards with no visible roles
    var companyCards = document.querySelectorAll("#oppsGrid .company-card");
    companyCards.forEach(function (card) {
      var roles = card.querySelectorAll("tr.opp-row:not(.hidden)");
      card.classList.toggle("card-hidden", roles.length === 0);
    });
    var empty = document.getElementById("oppsEmpty");
    if (empty) { empty.style.display = hasMatches ? "none" : ""; }
  }

  function updateCounts() {
    var dirCount = document.querySelectorAll("#directoryGrid .org-card:not(.card-hidden)").length;
    var oppsCount = document.querySelectorAll("#oppsGrid .company-card:not(.card-hidden)").length;
    var statDir = document.querySelector('.stat-card[data-view="directory"] .stat-value');
    var statOpps = document.querySelector('.stat-card[data-view="opportunities"] .stat-value');
    if (statDir) { statDir.textContent = dirCount.toLocaleString("en-IN"); }
    if (statOpps) { statOpps.textContent = oppsCount.toLocaleString("en-IN"); }
    if (roleCountBadge) { roleCountBadge.textContent = document.querySelectorAll("#oppsGrid .company-card:not(.card-hidden)").length + " companies"; }
  }

  // Event listeners
  document.querySelectorAll('.stat-card[data-view="directory"]').forEach(function (c) {
    c.addEventListener("click", function () { setView("directory", c.getAttribute("data-filter")); });
  });
  document.querySelectorAll('.stat-card[data-view="opportunities"]').forEach(function (c) {
    c.addEventListener("click", function () { setView("opportunities", c.getAttribute("data-filter")); });
  });
  [
    { id: "tabAll", view: "directory", filter: "all" },
    { id: "tabTech", view: "directory", filter: "tech_unicorn" },
    { id: "tabIndian", view: "directory", filter: "indian_tech" },
    { id: "tabOss", view: "directory", filter: "open_source" },
    { id: "tabRes", view: "directory", filter: "research_institute" },
    { id: "tabAllOpps", view: "opportunities", filter: "all" },
    { id: "tabInternship", view: "opportunities", filter: "internship" },
    { id: "tabEntry", view: "opportunities", filter: "entry_level" },
    { id: "tabRemote", view: "opportunities", filter: "remote" },
    { id: "tabUsSp500", view: "opportunities", filter: "us_sp500" },
    { id: "tabIndianTech", view: "opportunities", filter: "indian_tech" },
  ].forEach(function (t) {
    var btn = document.getElementById(t.id);
    if (btn) { btn.addEventListener("click", function () { setView(t.view, t.filter); }); }
  });

  // Search input handlers
  ["dirSearchInput", "roleSearchInput"].forEach(function (id) {
    var input = document.getElementById(id);
    if (input) { input.addEventListener("input", applyFilters); }
  });
  function applyFilters() {
    state.dirSearch = (document.getElementById("dirSearchInput") || {value: ""}).value.trim().toLowerCase();
    state.roleSearch = (document.getElementById("roleSearchInput") || {value: ""}).value.trim().toLowerCase();
    applyDirFilters();
    applyOppFilters();
    updateCounts();
  }

  window.addEventListener("hashchange", function () {
    var hash = location.hash || "#directory";
    if (hash === "#directory") { setView("directory"); }
    else if (hash === "#opportunities") { setView("opportunities"); }
  });
  // Shorten the long directory placeholder on small screens.
  function fitPlaceholders() {
    var dir = document.getElementById("dirSearchInput");
    if (dir) {
      dir.placeholder = window.innerWidth < 620
        ? "Search organizations…"
        : "Search 1,120+ verified organizations by name, ticker, or country…";
    }
    var role = document.getElementById("roleSearchInput");
    if (role) {
      role.placeholder = window.innerWidth < 620
        ? "Search live roles…"
        : "Search live roles by title, company, location, or class…";
    }
  }
  window.addEventListener("resize", fitPlaceholders);
  fitPlaceholders();
  setTimeout(function () {
    if (location.hash === "#opportunities") { setView("opportunities"); }
  }, 0);
  setView(location.hash === "#opportunities" ? "opportunities" : "directory");
})();
</script>

</body>
</html>"""


def classify_opportunity(o: Opportunity) -> tuple[str, str, str]:
    """Classify an opportunity into (role_type_slug, badge_text, badge_class)."""
    combined = (
        (o.title or "")
        + " "
        + (o.company_name or "")
        + " "
        + " ".join(o.locations or [])
        + " "
        + (o.work_mode.value or "")
    )
    combined_lower = combined.lower()
    if INTERN_REGEX.search(combined_lower):
        return "internship", "Internship", "badge-internship"
    if ENTRY_REGEX.search(combined_lower):
        return "entry_level", "Entry-Level", "badge-entry"
    return "general", "General", "badge-general"


def get_country_badge(country: str) -> str:
    """Return user-friendly country name."""
    c = country.lower() if country else ""
    if "united states" in c or c == "us" or "usa" in c or "america" in c:
        return "🇺🇸 United States"
    elif "india" in c:
        return "🇮🇳 India"
    elif "china" in c:
        return "🇨🇳 China"
    elif "uk" in c or "united kingdom" in c:
        return "🇬🇧 United Kingdom"
    elif "germany" in c:
        return "🇩🇪 Germany"
    elif "france" in c:
        return "🇫🇷 France"
    elif "japan" in c:
        return "🇯🇵 Japan"
    elif "singapore" in c:
        return "🇸🇬 Singapore"
    elif "canada" in c:
        return "🇨🇦 Canada"
    elif "switzerland" in c:
        return "🇨🇭 Switzerland"
    elif "netherlands" in c:
        return "🇳🇱 Netherlands"
    elif "australia" in c:
        return "🇦🇺 Australia"
    elif "brazil" in c:
        return "🇧🇷 Brazil"
    elif "south africa" in c:
        return "🇿🇦 South Africa"
    elif "spain" in c:
        return "🇪🇸 Spain"
    elif "uae" in c or "united arab emirates" in c:
        return "🇦🇪 UAE"
    else:
        return f"🌐 {country}" if country else "🌐 Not disclosed"


def get_category_label(category: str) -> str:
    """Return user-friendly category name."""
    mapping = {
        "us_sp500": "🏢 S&P 500 / US Listed",
        "indian_listed": "🇮🇳 BSE / NSE Listed",
        "tech_unicorn": "🦄 Tech Unicorn",
        "open_source": "🌐 Open Source Foundation",
        "research_institute": "🔬 Research Institute",
        "indian_tech": "🇮🇳 Indian Tech",
    }
    return mapping.get(category, category or "General")


class LocalViewerHandler(BaseHTTPRequestHandler):
    config: Config
    repo: Repository
    _last_rendered: bytes = b""  # test seam

    def do_GET(self) -> None:
        """Render the OpenPath viewer page (live roles + verified directory).

        Sends HTTP 200 on success, 404 for unknown paths, and 500 (with the
        traceback in the body) if the render fails — do_GET historically had
        no exception handling, which closed the connection without a response.
        """
        parsed_path = urlparse(self.path).path
        viewer_paths = (
            "/",
            "/opportunities",
            "/roles",
            "/jobs",
            "/directory",
            "/verified",
            "/verified-organizations",
            "/directory-organizations",
        )
        if parsed_path not in viewer_paths:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        try:
            body = self._render_page()
        except Exception as exc:
            # always answer HTTP so browsers show an error page, not a reset.
            logger.exception("OpenPath viewer page render failed")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc) or "Internal Error")
            return
        LocalViewerHandler._last_rendered = body
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render_page(self) -> bytes:
        """Render the page HTML. Separated from do_GET so it can be tested
        without a real socket."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        search_query = params.get("q", [None])[0]

        opps = self.repo.list_opportunities(search_query=search_query, limit=10000)
        all_orgs = self.repo.list_organisations(limit=5000)
        verified_count = sum(1 for o in opps if o.admission_class == "VERIFIED")
        internship_count = 0
        entry_count = 0
        student_friendly_count = 0
        remote_count = 0
        sp500_opps_count = 0
        indian_tech_opps_count = 0

        # Group opportunities by company
        grouped: dict[str, list[Opportunity]] = {}
        for o in opps:
            grouped.setdefault(o.company_name, []).append(o)

        cards_html: list[str] = []
        for company_name, company_opps in sorted(
            grouped.items(), key=lambda x: len(x[1]), reverse=True
        ):
            meta = COMPANY_METADATA.get(company_name, {})
            ticker = meta.get("ticker", "Authoritative Declared Source")
            category = meta.get("category", "general")
            initial = meta.get("avatar") or (company_name[:2].upper() if company_name else "OP")
            avatar_color = meta.get("color") or "#238636"
            total_jobs = len(company_opps)
            intern_cnt = sum(1 for o in company_opps if classify_opportunity(o)[0] == "internship")
            entry_cnt = sum(1 for o in company_opps if classify_opportunity(o)[0] == "entry_level")
            remote_cnt = sum(1 for o in company_opps if o.work_mode.value in ("remote", "hybrid"))

            internship_count += intern_cnt
            entry_count += entry_cnt
            student_friendly_count += intern_cnt + entry_cnt
            remote_count += remote_cnt
            sp500_opps_count += sum(1 for o in company_opps if category == "us_sp500")
            indian_tech_opps_count += sum(
                1 for o in company_opps if category in ("indian_tech", "indian_listed")
            )

            cards_html.append(
                f"<details open class='company-card' data-company='{html.escape(company_name)}' data-category='{html.escape(category)}'>\n"
                f"  <summary class='company-summary'>\n"
                f"    <div class='company-header-left'>\n"
                f"      <div class='company-avatar' style='background: {avatar_color};'>{initial}</div>\n"
                f"      <div class='company-title-block'>\n"
                f"        <h2 class='company-title' title='{html.escape(company_name)}'>{html.escape(company_name)}</h2>\n"
                f"        <span class='company-ticker' title='{html.escape(ticker)}'>({html.escape(ticker)})</span>\n"
                f"      </div>\n"
                f"    </div>\n"
                f"    <div class='company-badges'>\n"
                f"      <span class='badge badge-live' style='cursor:pointer;' onclick='filterOppCompany(\"{html.escape(company_name)}\")'>🔥 {total_jobs} Live Roles</span>\n"
                f"      <span class='badge badge-remote'>🏢 {intern_cnt + entry_cnt} Intern/Entry</span>\n"
                f"      <span class='badge badge-hybrid'>🌐 {remote_cnt} Remote</span>\n"
                f"    </div>\n"
                f"  </summary>\n"
                f"  <div class='company-roles'>\n"
                f"    <table class='opportunities-table'>\n"
                f"      <thead><tr><th>Role</th><th>Type</th><th>Location</th><th>Mode</th><th>Class</th><th></th></tr></thead>\n"
                f"      <tbody>\n"
                f"        {''.join(self._render_company_role_rows(company_opps))}\n"
                f"      </tbody>\n"
                f"    </table>\n"
                f"  </div>\n"
                f"</details>"
            )

        cards_output = (
            "\n".join(cards_html)
            if cards_html
            else "<div class='empty-state'><h3>No opportunities found</h3><p>Try refining your search keyword or run new source discovery.</p></div>"
        )

        # Directory cards for verified organisations
        dir_cards_html: list[str] = []
        avatar_palette = [
            "#238636",
            "#1f6feb",
            "#8957e5",
            "#da3633",
            "#d29922",
            "#00d09c",
            "#f38020",
            "#3ecf8e",
        ]
        sp500_orgs_count = 0
        indian_orgs_count = 0
        unicorn_orgs_count = 0
        oss_orgs_count = 0
        res_orgs_count = 0
        for idx, org in enumerate(all_orgs):
            cat = org["category"]
            if cat == "us_sp500":
                sp500_orgs_count += 1
            elif cat == "indian_listed":
                indian_orgs_count += 1
            elif cat == "tech_unicorn":
                unicorn_orgs_count += 1
            elif cat == "open_source":
                oss_orgs_count += 1
            elif cat == "research_institute":
                res_orgs_count += 1
            cname = org["canonical_name"]
            lname = org["legal_name"]
            initial = cname[:2].upper() if len(cname) >= 2 else "OP"
            av_color = avatar_palette[idx % len(avatar_palette)]
            country_badge = get_country_badge(org["country"])
            category_badge = get_category_label(cat)
            live_jobs = org["live_jobs_count"]
            live_jobs_badge = ""
            if live_jobs > 0:
                live_jobs_badge = (
                    f"<button type='button' class='badge badge-hot' style='cursor:pointer;' onclick='filterOppCompany(\"{html.escape(cname)}\")'>"
                    f"🔥 {live_jobs} Live Roles"
                    f"</button>"
                )
            dir_cards_html.append(
                f"<div class='org-card' data-category='{html.escape(cat)}' data-name='{html.escape(cname.lower())}' data-ticker='{html.escape(org['registry_id'].lower())}' data-country='{html.escape(org['country'].lower())}'>\n"
                f"  <div>\n"
                f"    <div class='org-header'>\n"
                f"      <div class='avatar' style='background: {av_color};'>{initial}</div>\n"
                f"      <div>\n"
                f"        <h3 class='org-title'>{html.escape(cname)}</h3>\n"
                f"        <p class='org-legal'>{html.escape(lname)}</p>\n"
                f"      </div>\n"
                f"      <span class='badge badge-verified'>✓ PASS</span>\n"
                f"    </div>\n"
                f"    <div class='org-meta-badges'>\n"
                f"      <span class='badge badge-onsite'>{html.escape(country_badge)}</span>\n"
                f"      <span class='badge badge-onsite' style='color:#58a6ff;'>{html.escape(category_badge)}</span>\n"
                f"      <span class='badge badge-onsite' style='color:#e3b341;'>{html.escape(org['registry_id'])}</span>\n"
                f"    </div>\n"
                f"  </div>\n"
                f"  <div class='org-footer'>\n"
                f"    <div>{live_jobs_badge}</div>\n"
                f"    <div class='org-actions'>\n"
                f"      <a class='btn btn-apply' href='{html.escape(org['website_url'])}' target='_blank' rel='noopener noreferrer'>Careers Portal ↗</a>\n"
                f"    </div>\n"
                f"  </div>\n"
                f"</div>"
            )

        directory_output = "\n".join(dir_cards_html)

        body = (
            HTML_TEMPLATE.replace("{total_verified_orgs}", f"{len(all_orgs):,}")
            .replace("{total_opportunities}", f"{len(opps):,}")
            .replace("{verified_count}", f"{verified_count:,}")
            .replace("{internship_count}", str(internship_count))
            .replace("{entry_count}", str(entry_count))
            .replace("{student_friendly_count}", str(student_friendly_count))
            .replace("{remote_count}", str(remote_count))
            .replace("{sp500_opps_count}", str(sp500_opps_count))
            .replace("{indian_tech_opps_count}", str(indian_tech_opps_count))
            .replace("{sp500_orgs_count}", str(sp500_orgs_count))
            .replace("{indian_orgs_count}", str(indian_orgs_count))
            .replace("{unicorn_orgs_count}", str(unicorn_orgs_count))
            .replace("{oss_orgs_count}", str(oss_orgs_count))
            .replace("{res_orgs_count}", str(res_orgs_count))
            .replace("{query}", html.escape(search_query or ""))
            .replace("{cards}", cards_output)
            .replace("{directory_cards}", directory_output)
            .encode("utf-8")
        )
        LocalViewerHandler._last_rendered = body
        return body

    def _render_company_role_rows(self, company_opps: list[Opportunity]) -> list[str]:
        """Render one <tr> per opportunity in a company card."""
        rows: list[str] = []
        for o in company_opps:
            role_type, role_badge_text, role_badge_class = classify_opportunity(o)
            badge_cls = "badge-verified" if o.admission_class == "VERIFIED" else "badge-lead"
            mode_cls = (
                f"badge-{o.work_mode.value}"
                if o.work_mode.value in ("remote", "hybrid", "onsite")
                else "badge-onsite"
            )
            rows.append(
                f"<tr class='opp-row' data-role-type='{role_type}' data-work-mode='{o.work_mode.value}'>"
                f"<td><a class='title' href='{html.escape(o.canonical_application_url)}' target='_blank' rel='noopener noreferrer'>{html.escape(o.title)}</a></td>"
                f"<td><span class='badge {role_badge_class}'>{html.escape(role_badge_text)}</span></td>"
                f"<td class='muted'>{html.escape(', '.join(o.locations) if o.locations else 'Not disclosed')}</td>"
                f"<td><span class='badge {mode_cls}'>{html.escape(o.work_mode.value)}</span></td>"
                f"<td><span class='badge {badge_cls}'>{html.escape(o.admission_class)}</span></td>"
                f"<td><a class='btn btn-apply' href='{html.escape(o.canonical_application_url)}' target='_blank' rel='noopener noreferrer'>Apply ↗</a></td>"
                f"</tr>"
            )
        return rows

    def log_message(self, format: str, *args: object) -> None:
        logger.info(
            "%s - - [%s] %s\n", self.address_string(), self.log_date_time_string(), format % args
        )


def run_server(config: Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    """Launch the local read-only web inspector."""
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError(
            f"Security violation: OpenPath local web viewer can ONLY bind to 127.0.0.1 or localhost (attempted: {host})."
        )

    handler_cls = type(
        "ConfiguredLocalViewerHandler",
        (LocalViewerHandler,),
        {"config": config, "repo": Repository(DatabaseManager(config.db_path))},
    )

    # Ensure the database schema exists before serving: a viewer over an
    # empty/unmigrated DB used to crash silently per-request.
    _db_mgr = DatabaseManager(config.db_path)
    with _db_mgr.connection() as _conn:
        apply_migrations(_conn)

    server = HTTPServer((host, port), handler_cls)
    print(f"\n✓ OpenPath Local Web Viewer running at http://{host}:{port}/")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
