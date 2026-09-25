const $ = (id) => document.getElementById(id);

const API = {
  health: "/api/health",
  catalog: "/api/catalog",
  shortlist: "/api/shortlist",
  researchStatus: "/api/research/status",
  researchJobs: "/api/research/jobs",
  integrations: "/api/integrations",
  foundersSync: "/api/integrations/founders/sync",
};

const PILLARS = [
  { key: "founders", label: "Founders & leadership", short: "Leadership" },
  { key: "business", label: "Business & market", short: "Business" },
  { key: "funding", label: "Funding & financial", short: "Funding" },
  { key: "reputation", label: "Reputation & interest", short: "Reputation" },
];

const RECORD_LABELS = {
  research: "Research profile",
  filing: "SEC filing record",
  lead: "Team research lead",
};

const SIGNALS = [
  { key: "momentum", label: "Recent raise" },
  { key: "repeat", label: "Repeat raises" },
  { key: "investors", label: "Investor breadth" },
  { key: "hiring", label: "Hiring" },
  { key: "accelerator", label: "Accelerator / program" },
  { key: "ip", label: "IP & partnerships" },
  { key: "grants", label: "Public grants" },
];

const SIGNAL_GUIDE = [
  { key: "capital", label: "Capital raised", max: 20, full: "$50M or more reported sold (log scale from $50K)", source: "SEC Form D filings" },
  { key: "momentum", label: "Recent raise", max: 20, full: "Latest round within 6 months (16 within a year, 10 within 2 years, 4 within 3)", source: "SEC Form D filing dates" },
  { key: "hiring", label: "Hiring", max: 15, full: "50+ employees added per year since founding", source: "Headcount research" },
  { key: "repeat", label: "Repeat raises", max: 10, full: "3 or more separate rounds (7 for 2 rounds)", source: "SEC Form D filings" },
  { key: "investors", label: "Investor breadth", max: 10, full: "25 or more investors across rounds", source: "SEC Form D filings" },
  { key: "accelerator", label: "Accelerator / program", max: 10, full: "Accelerator or program selection (awards add 5)", source: "Sourced reputation research" },
  { key: "ip", label: "IP & research partnerships", max: 10, full: "Two of: technology license, research collaboration, industry partnership", source: "Sourced reputation research" },
  { key: "grants", label: "Public grants", max: 5, full: "Any linked public grant record", source: "Founder and grant records" },
];

const TIER_GUIDE = [
  { key: "high", label: "High signal", range: "50–100", text: "Several strong signals at once, usually recent money from many investors." },
  { key: "elevated", label: "Elevated", range: "35–49", text: "Clear momentum on a few signals." },
  { key: "moderate", label: "Moderate", range: "15–34", text: "Some activity, often a single funding round." },
  { key: "low", label: "Low", range: "0–14", text: "Little public evidence so far. Not the same as a weak company." },
];

// Fixed categorical order so a cluster keeps its color under every filter.
const CLUSTER_COLORS = {
  tech: "#2a78d6",
  life: "#eb6834",
  climate: "#1baf7a",
  industrial: "#eda100",
  fintech: "#e87ba4",
  consumer: "#008300",
  services: "#4a3aa7",
  other: "#898781",
};

const SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];

const TERMINAL_RESEARCH_STATES =new Set(["completed", "partial", "failed", "interrupted"]);
const numberFormatter = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

const state = {
  catalog: [],
  sectors: [],
  stats: {},
  notices: [],
  snapshotDate: "",
  catalogLoading: true,
  catalogError: "",
  view: "directory",
  page: 1,
  filters: {
    query: "",
    hideNonStartups: true,
    nj: "all",
    sector: "all",
    recordType: "all",
    cluster: "all",
    minScore: 0,
    youngOnly: false,
    signals: [],
    sort: "signal",
    perPage: 24,
  },
  shownFilters: [],
  sectorView: null,
  trendMetric: "rounds",
  regionCluster: "all",
  selectedSector: "",
  shortlist: { ids: [], notes: {} },
  shortlistBusy: new Set(),
  shortlistQueue: Promise.resolve(),
  compareIds: [],
  detailCompany: null,
  detailFallback: false,
  detailGeneration: 0,
  auth: {
    healthKnown: false,
    serverOk: false,
    required: false,
    token: "",
  },
  research: {
    status: null,
    statusError: "",
    job: null,
    history: [],
    timer: null,
    generation: 0,
    failures: 0,
    busy: false,
    refreshedJobs: new Set(),
  },
  integrations: null,
  integrationsError: "",
};

let activeLayer = null;
let layerReturnFocus = null;

class ApiError extends Error {
  constructor(message, status = 0, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#39;",
    '"': "&quot;",
  })[character]);
}

function icon(name, className = "") {
  const safeName = String(name).replace(/[^a-z-]/g, "");
  const safeClass = String(className).replace(/[^a-zA-Z0-9 _-]/g, "");
  return `<svg${safeClass ? ` class="${safeClass}"` : ""} aria-hidden="true"><use href="#icon-${safeName}"></use></svg>`;
}

function safeUrl(value) {
  if (!value) return null;
  try {
    const url = new URL(String(value));
    return ["https:", "http:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function formatNumber(value) {
  return numberFormatter.format(finiteNumber(value));
}

function formatDate(value, options = { month: "short", day: "numeric", year: "numeric" }) {
  if (!value) return "Not reported";
  const raw = String(value).trim();
  if (/^\d{4}$/.test(raw)) return raw;
  if (/^\d{4}-\d{2}$/.test(raw)) {
    const monthDate = new Date(`${raw}-01T12:00:00`);
    return Number.isNaN(monthDate.valueOf()) ? raw : monthDate.toLocaleDateString(undefined, { month: "short", year: "numeric" });
  }
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? `${raw}T12:00:00` : raw;
  const date = new Date(normalized);
  if (Number.isNaN(date.valueOf())) return raw;
  return date.toLocaleDateString(undefined, options);
}

function sentenceCase(value) {
  const text = String(value ?? "").replaceAll("_", " ").trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Unknown";
}

function plural(count, singular, pluralForm = `${singular}s`) {
  return `${formatNumber(count)} ${count === 1 ? singular : pluralForm}`;
}

function initials(name) {
  const parts = String(name || "Company").trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part.charAt(0)).join("").toUpperCase() || "CO";
}

function companyById(id) {
  return state.catalog.find((company) => String(company.id) === String(id)) || null;
}

function pillarFor(company, key) {
  const raw = asObject(asObject(company?.pillars)[key]);
  const status = ["available", "partial", "missing"].includes(raw.status) ? raw.status : "missing";
  return {
    status,
    summary: String(raw.summary || ""),
    metrics: asArray(raw.metrics),
    findings: asArray(raw.findings),
    limitations: asArray(raw.limitations),
  };
}

function coverageCount(company) {
  if (Number.isFinite(Number(company?.coverage_count))) return Number(company.coverage_count);
  return PILLARS.filter(({ key }) => pillarFor(company, key).status !== "missing").length;
}

function normalizedText(value) {
  return String(value ?? "").toLocaleLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
}

function isLikelyNonStartup(company) {
  return asArray(company?.tags).some((tag) => normalizedText(tag).startsWith("non-startup classification:"));
}

function debounce(callback, wait = 160) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => callback(...args), wait);
  };
}

function uniqueStrings(values) {
  return [...new Set(asArray(values).map((value) => String(value || "").trim()).filter(Boolean))];
}

function requestId() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return `garden-state-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function apiFetch(path, options = {}, { publicEndpoint = false } = {}) {
  const { timeout = 20000, ...fetchOptions } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  if (state.auth.token && !publicEndpoint) headers.set("Authorization", `Bearer ${state.auth.token}`);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  try {
    const response = await fetch(path, { ...fetchOptions, headers, signal: controller.signal });
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = { message: text };
      }
    }

    if (!response.ok) {
      const message = payload?.detail || payload?.error || payload?.message || `Request failed (${response.status}).`;
      if (response.status === 401 && !publicEndpoint) handleUnauthorized();
      throw new ApiError(String(message), response.status, payload);
    }
    return payload ?? {};
  } catch (error) {
    if (error.name === "AbortError") throw new ApiError("The server took too long to respond. Try again.");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Could not reach the Garden State server.");
  } finally {
    clearTimeout(timer);
  }
}

function handleUnauthorized() {
  const hadToken = Boolean(state.auth.token);
  clearTimeout(state.research.timer);
  state.research.generation += 1;
  state.research.busy = false;
  closeLayer({ restoreFocus: false });
  closeSidebar();
  state.auth.required = true;
  state.auth.token = "";
  renderAuthState();
  if (hadToken) toast("That token was rejected or expired. Unlock the workspace again.", "error");
}

function toast(message, tone = "success", duration = 4200) {
  const region = $("toast-region");
  const item = document.createElement("div");
  item.className = `toast${tone === "error" ? " is-error" : tone === "warning" ? " is-warning" : ""}`;
  item.innerHTML = `${icon(tone === "error" || tone === "warning" ? "warning" : "check")}<p>${escapeHTML(message)}</p><button type="button" data-close-toast aria-label="Dismiss notification">${icon("close")}</button>`;
  region.append(item);
  const remove = () => {
    if (!item.isConnected) return;
    item.style.opacity = "0";
    item.style.transform = "translateX(12px)";
    setTimeout(() => item.remove(), 180);
  };
  item.querySelector("[data-close-toast]").addEventListener("click", remove);
  setTimeout(remove, duration);
}

function renderHealth() {
  const pill = $("health-pill");
  const dot = pill.querySelector(".status-dot");
  dot.className = "status-dot";
  if (!state.auth.healthKnown) {
    dot.classList.add("is-loading");
    $("health-label").textContent = "Connecting";
    return;
  }
  if (!state.auth.serverOk) {
    dot.classList.add("is-error");
    $("health-label").textContent = "Connection issue";
    return;
  }
  if (state.auth.required && !state.auth.token) {
    dot.classList.add("is-error");
    $("health-label").textContent = "Locked";
    return;
  }
  $("health-label").textContent = state.auth.required ? "Unlocked" : "Connected";
}

function renderAuthState() {
  renderHealth();
  const locked = state.auth.required && !state.auth.token;
  $("access-gate").hidden = !locked;
  $("directory-section").hidden = locked || ["sectors", "scoring"].includes(state.view);
  $("hero-count").hidden = locked;

  const title = $("session-access-title");
  const copy = $("session-access-copy");
  const form = $("settings-unlock-form");
  if (!state.auth.healthKnown) {
    title.textContent = "Checking server access";
    copy.textContent = "The connection check is still running.";
    form.hidden = true;
  } else if (state.auth.required && state.auth.token) {
    title.textContent = "Unlocked for this tab";
    copy.textContent = "The token lives in memory and disappears when this tab closes.";
    form.hidden = true;
  } else if (state.auth.required) {
    title.textContent = "Token required";
    copy.textContent = "Unlock access here or from the main workspace. Nothing is saved in the browser.";
    form.hidden = false;
  } else {
    title.textContent = "No token required";
    copy.textContent = "This server is available to the current session without an access token.";
    form.hidden = true;
  }
}

async function loadHealth() {
  try {
    const health = await apiFetch(API.health, {}, { publicEndpoint: true });
    state.auth.serverOk = health.status === "ok" || health.status === "healthy";
    state.auth.required = Boolean(health.auth_required);
  } catch {
    state.auth.serverOk = false;
    state.auth.required = false;
  } finally {
    state.auth.healthKnown = true;
    renderAuthState();
  }
}

async function unlockWorkspace(token, messageElement, submitButton) {
  const cleanToken = String(token || "").trim();
  if (!cleanToken) {
    messageElement.textContent = "Enter an access token first.";
    return;
  }
  const originalHTML = submitButton.innerHTML;
  submitButton.disabled = true;
  submitButton.textContent = "Checking…";
  messageElement.textContent = "";
  state.auth.token = cleanToken;
  try {
    const catalog = await apiFetch(API.catalog);
    state.auth.serverOk = true;
    applyCatalog(catalog);
    renderAuthState();
    await Promise.allSettled([loadShortlist(), loadResearchStatus()]);
    if (!$("methodology-layer").hidden) await loadIntegrations();
    $("access-token").value = "";
    $("settings-access-token").value = "";
    toast("Workspace unlocked for this tab.");
  } catch (error) {
    state.auth.token = "";
    renderAuthState();
    messageElement.textContent = error.status === 401 ? "That token didn’t work." : error.message;
  } finally {
    submitButton.disabled = false;
    submitButton.innerHTML = originalHTML;
  }
}

function applyCatalog(payload) {
  const openDetailId = !$("company-layer").hidden && state.detailCompany ? String(state.detailCompany.id) : "";
  const companies = asArray(payload?.companies).filter((company) => company && company.id != null);
  state.catalog = companies;
  state.sectors = uniqueStrings(payload?.sectors).sort((a, b) => a.localeCompare(b));
  state.stats = asObject(payload?.stats);
  state.notices = uniqueStrings(payload?.notices);
  state.snapshotDate = String(payload?.snapshot_date || "");
  state.sectorView = payload?.sector_view && typeof payload.sector_view === "object" ? payload.sector_view : null;
  state.catalogLoading = false;
  state.catalogError = "";
  state.auth.serverOk = true;
  populateSectorFilters();
  renderCatalogChrome();
  renderDirectory();
  renderSectors();
  renderScoring();
  renderCompareState({ directory: false });
  if (openDetailId) {
    const rebound = companyById(openDetailId);
    if (rebound) renderCompanyDrawer(rebound, { fallback: state.detailFallback });
  }
}

async function loadCatalog({ quiet = false } = {}) {
  if (!quiet && !state.catalog.length) {
    state.catalogLoading = true;
    state.catalogError = "";
    renderDirectory();
  }
  try {
    const payload = await apiFetch(API.catalog);
    applyCatalog(payload);
    return payload;
  } catch (error) {
    if (error.status === 401) return null;
    if (!state.catalog.length) {
      state.catalogLoading = false;
      state.catalogError = error.message;
      renderDirectory();
    } else {
      toast(`The catalog could not refresh: ${error.message}`, "warning");
    }
    throw error;
  }
}

function renderCatalogChrome() {
  const stats = state.stats;
  const companyTotal = finiteNumber(stats.companies, state.catalog.length);
  $("directory-count").textContent = formatNumber(companyTotal);
  $("sidebar-snapshot").textContent = state.snapshotDate ? `Data as of ${formatDate(state.snapshotDate)}` : "Data date not reported";
  const startups = state.catalog.filter((company) => !isLikelyNonStartup(company)).length;
  $("hero-count").innerHTML = `<strong>${formatNumber(startups)}</strong> New Jersey companies found${state.snapshotDate ? ` · data as of ${escapeHTML(formatDate(state.snapshotDate))}` : ""}`;
  $("catalog-notices").innerHTML = state.notices.map((notice) => `<li>${escapeHTML(notice)}</li>`).join("");
}

function populateSelect(select, values, firstOption, preferredValue) {
  const selected = preferredValue ?? select.value;
  select.innerHTML = `<option value="${escapeHTML(firstOption.value)}">${escapeHTML(firstOption.label)}</option>${values.map((value) => `<option value="${escapeHTML(value)}">${escapeHTML(value)}</option>`).join("")}`;
  select.value = [...select.options].some((option) => option.value === selected) ? selected : firstOption.value;
}

function populateSectorFilters() {
  populateSelect($("sector-filter"), state.sectors, { value: "all", label: "All sectors" }, state.filters.sector);
  const researchSectors = uniqueStrings(state.research.status?.sectors?.length ? state.research.status.sectors : state.sectors);
  populateSelect($("research-sector"), researchSectors, { value: "All sectors", label: "All sectors" });
  const clusters = asArray(state.sectorView?.clusters);
  const clusterOptions = `<option value="all">All clusters</option>${clusters.map((cluster) => `<option value="${escapeHTML(cluster.key)}">${escapeHTML(cluster.label)}</option>`).join("")}`;
  for (const [id, current] of [["cluster-filter", state.filters.cluster], ["region-cluster", state.regionCluster]]) {
    const select = $(id);
    select.innerHTML = clusterOptions;
    select.value = [...select.options].some((option) => option.value === current) ? current : "all";
  }
  $("signal-chips").innerHTML = SIGNALS.map(({ key, label }) => {
    const active = state.filters.signals.includes(key);
    return `<button type="button" class="signal-chip${active ? " is-active" : ""}" data-signal-chip="${key}" aria-pressed="${active}">${escapeHTML(label)}</button>`;
  }).join("");
}

function signalScore(company) {
  const score = asObject(company?.signal_score);
  return { ...score, total: finiteNumber(score.total), components: asArray(score.components), signals: asArray(score.signals) };
}

function scoreBadge(company, className = "") {
  const score = signalScore(company);
  const tier = String(score.tier || "low");
  return `<span class="score-badge tier-${escapeHTML(tier)} ${className}" title="Signal score ${score.total}/100 · ${escapeHTML(score.tier_label || "Low")}"><strong>${score.total}</strong><small>${escapeHTML(score.tier_label || "Low")}</small></span>`;
}

function scoreBreakdown(company) {
  const score = signalScore(company);
  const rows = score.components.map((component) => {
    const item = asObject(component);
    const max = finiteNumber(item.max, 1);
    const points = finiteNumber(item.points);
    const width = Math.max(0, Math.min(100, (points / max) * 100));
    return `<div class="score-row${item.detected ? "" : " is-missing"}"><div class="score-row-head"><span>${escapeHTML(item.label || "Signal")}</span><strong>${item.detected ? `${Number(points.toFixed(1))} / ${max}` : `Not detected · 0 / ${max}`}</strong></div><div class="score-track" aria-hidden="true"><span style="width:${width}%"></span></div><small>${escapeHTML(item.detail || "")}</small></div>`;
  }).join("");
  return `<section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Signal score</p><h3>${score.total}/100 · ${escapeHTML(score.tier_label || "Low")}</h3></div><span>${plural(score.signals.length, "signal")} detected</span></div><div class="score-breakdown">${rows}</div><p class="score-note">Points come only from observed signals. Missing data scores zero and is labeled, so a low score can mean little public evidence rather than a weak company.</p></section>`;
}

function getFilteredCompanies() {
  const shortlistIds = new Set(state.shortlist.ids.map(String));
  const query = normalizedText(state.filters.query);
  const tokens = query.split(/\s+/).filter(Boolean);
  let companies = state.catalog.filter((company) => {
    if (state.view === "shortlist" && !shortlistIds.has(String(company.id))) return false;
    if (state.view === "directory" && state.filters.hideNonStartups && isLikelyNonStartup(company)) return false;
    if (state.filters.nj !== "all" && company.nj_status !== state.filters.nj) return false;
    if (state.filters.sector !== "all" && company.sector !== state.filters.sector) return false;
    if (state.filters.recordType !== "all" && company.record_type !== state.filters.recordType) return false;
    if (state.filters.cluster !== "all" && company.cluster !== state.filters.cluster) return false;
    if (state.filters.youngOnly && !asArray(company.tags).includes("young company")) return false;
    const score = signalScore(company);
    if (score.total < state.filters.minScore) return false;
    if (state.filters.signals.some((key) => !score.signals.includes(key))) return false;
    if (!tokens.length) return true;
    const peopleText = asArray(company.people).map((person) => `${person?.name || ""} ${person?.role || ""}`).join(" ");
    const searchable = normalizedText([
      company.name,
      company.description,
      company.sector,
      company.location,
      company.why_surfaced,
      ...asArray(company.tags),
      peopleText,
    ].join(" "));
    return tokens.every((token) => searchable.includes(token));
  });

  const sorters = {
    signal: (a, b) => signalScore(b).total - signalScore(a).total || signalScore(b).signals.length - signalScore(a).signals.length || String(a.name || "").localeCompare(String(b.name || "")),
    name:(a, b) => String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
    coverage: (a, b) => coverageCount(b) - coverageCount(a) || finiteNumber(b.source_count) - finiteNumber(a.source_count) || String(a.name || "").localeCompare(String(b.name || "")),
    sources: (a, b) => finiteNumber(b.source_count) - finiteNumber(a.source_count) || coverageCount(b) - coverageCount(a) || String(a.name || "").localeCompare(String(b.name || "")),
    updated: (a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || String(a.name || "").localeCompare(String(b.name || "")),
  };
  if (state.filters.sort === "research") return companies;
  companies = [...companies].sort(sorters[state.filters.sort] || sorters.name);
  return companies;
}

function filtersAreActive() {
  const f = state.filters;
  return Boolean(f.query || !f.hideNonStartups || f.nj !== "all" || f.sector !== "all" || f.recordType !== "all" || f.cluster !== "all" || f.minScore || f.youngOnly || f.signals.length || f.sort !== "signal");
}

function companyCard(company) {
  const id = String(company.id);
  const saved = state.shortlist.ids.map(String).includes(id);
  const compared = state.compareIds.includes(id);
  const busy = state.shortlistBusy.has(id);
  const statuses = PILLARS.map(({ key }) => pillarFor(company, key).status);
  const recordType = RECORD_LABELS[company.record_type] || sentenceCase(company.record_type || "Company record");
  const njSupported = company.nj_status === "supported";
  const likelyNonStartup = isLikelyNonStartup(company);
  const description = String(company.description || "No company description is attached to this record yet.");
  const location = String(company.location || "Location not reported");
  const reason = String(company.why_surfaced || "");

  return `
    <article class="company-card" data-card-id="${escapeHTML(id)}">
      <div class="company-card-head">
        <div class="company-avatar" aria-hidden="true">${escapeHTML(initials(company.name))}</div>
        <div class="company-title-wrap">
          <button class="company-title" type="button" data-open-company="${escapeHTML(id)}" title="${escapeHTML(company.name || "Company")}">${escapeHTML(company.name || "Unnamed company")}</button>
          <p class="company-location" title="${escapeHTML(location)}">${escapeHTML(location)}</p>
        </div>
        ${scoreBadge(company)}
        <button class="card-save${saved ? " is-saved" : ""}" type="button" data-toggle-save="${escapeHTML(id)}" aria-pressed="${saved}" aria-label="${saved ? "Remove" : "Add"} ${escapeHTML(company.name || "company")} ${saved ? "from" : "to"} shortlist" ${busy ? "disabled" : ""}>${icon("bookmark")}</button>
      </div>
      <div class="card-badges">
        <span class="badge ${njSupported ? "nj-supported" : "nj-unverified"}">${escapeHTML(njSupported ? "NJ evidence supported" : "NJ status unverified")}</span>
        ${company.sector ? `<span class="badge">${escapeHTML(company.sector)}</span>` : ""}
        <span class="badge">${escapeHTML(recordType)}</span>
        ${likelyNonStartup ? '<span class="badge likely-nonstartup">Likely non-startup entity</span>' : ""}
      </div>
      <p class="card-description">${escapeHTML(description)}</p>
      ${reason ? `<p class="why-surfaced"><strong>Why it surfaced:</strong> ${escapeHTML(reason)}</p>` : ""}
      <div class="card-evidence">
        <div class="coverage-head"><span>Evidence pillars</span><strong>${coverageCount(company)} of 4</strong></div>
        <div class="coverage-bar" aria-label="${coverageCount(company)} of 4 evidence pillars have coverage">${statuses.map((status, index) => `<span class="${escapeHTML(status)}" title="${escapeHTML(PILLARS[index].label)}: ${escapeHTML(status)}"></span>`).join("")}</div>
      </div>
      <div class="card-footer">
        <span class="source-count">${plural(finiteNumber(company.source_count), "linked source")}</span>
        <div class="card-actions">
          <button class="compare-toggle${compared ? " is-selected" : ""}" type="button" data-toggle-compare="${escapeHTML(id)}" aria-pressed="${compared}">${compared ? "Added" : "Compare"}</button>
          <button class="open-profile" type="button" data-open-company="${escapeHTML(id)}">Profile ${icon("arrow")}</button>
        </div>
      </div>
    </article>`;
}

function renderDirectory() {
  const loading = $("catalog-loading");
  const error = $("catalog-error");
  const grid = $("company-grid");
  const empty = $("empty-state");
  const pagination = $("pagination");

  if (state.catalogLoading && !state.catalog.length) {
    loading.hidden = false;
    error.hidden = true;
    grid.innerHTML = "";
    empty.hidden = true;
    pagination.innerHTML = "";
    $("results-summary").textContent = "Loading company records…";
    return;
  }

  loading.hidden = true;
  if (state.catalogError && !state.catalog.length) {
    error.hidden = false;
    $("catalog-error-message").textContent = state.catalogError;
    grid.innerHTML = "";
    empty.hidden = true;
    pagination.innerHTML = "";
    $("results-summary").textContent = "Catalog unavailable";
    return;
  }
  error.hidden = true;

  const filtered = getFilteredCompanies();
  const taggedNonStartups = state.catalog.filter(isLikelyNonStartup).length;
  const hiddenNonStartups = state.view === "directory" && state.filters.hideNonStartups ? taggedNonStartups : 0;
  $("startup-filter").disabled = state.view === "shortlist";
  $("nonstartup-filter-note").textContent = state.view === "shortlist"
    ? "Saved records are always shown"
    : taggedNonStartups
      ? `${formatNumber(taggedNonStartups)} tagged records ${state.filters.hideNonStartups ? "hidden" : "included"}`
      : "No classification tags reported";
  const pageCount = Math.max(1, Math.ceil(filtered.length / state.filters.perPage));
  state.page = Math.min(Math.max(1, state.page), pageCount);
  const start = (state.page - 1) * state.filters.perPage;
  const pageCompanies = filtered.slice(start, start + state.filters.perPage);

  const recordWord = state.view === "shortlist" ? "saved record" : "company record";
  if (filtered.length) {
    const from = start + 1;
    const to = Math.min(start + state.filters.perPage, filtered.length);
    $("results-summary").innerHTML = `Showing <strong>${formatNumber(from)}–${formatNumber(to)}</strong> of <strong>${formatNumber(filtered.length)}</strong> ${escapeHTML(filtered.length === 1 ? recordWord : `${recordWord}s`)}${hiddenNonStartups ? ` · ${formatNumber(hiddenNonStartups)} likely non-startups hidden` : ""}`;
  } else {
    $("results-summary").textContent = `0 ${recordWord}s`;
  }
  $("clear-filters").hidden = !filtersAreActive();

  grid.innerHTML = pageCompanies.map(companyCard).join("");
  empty.hidden = Boolean(pageCompanies.length);
  if (!pageCompanies.length) {
    if (state.view === "shortlist" && !state.shortlist.ids.length) {
      $("empty-title").textContent = "Your shortlist is empty.";
      $("empty-copy").textContent = "Save a company record and it will stay here with your notes.";
      empty.querySelector("[data-action='clear-filters']").hidden = true;
    } else {
      $("empty-title").textContent = "No records match these filters.";
      $("empty-copy").textContent = "Try a broader search or clear one of the filters.";
      empty.querySelector("[data-action='clear-filters']").hidden = false;
    }
  }
  renderPagination(pageCount);
}

function paginationItems(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const pages = new Set([1, total, current - 1, current, current + 1].filter((page) => page > 0 && page <= total));
  const sorted = [...pages].sort((a, b) => a - b);
  const items = [];
  sorted.forEach((page, index) => {
    if (index && page - sorted[index - 1] > 1) items.push("…");
    items.push(page);
  });
  return items;
}

function renderPagination(pageCount) {
  const nav = $("pagination");
  if (pageCount <= 1) {
    nav.innerHTML = "";
    return;
  }
  const numbered = paginationItems(state.page, pageCount).map((item) => item === "…"
    ? `<span class="page-ellipsis">…</span>`
    : `<button class="page-button${item === state.page ? " is-current" : ""}" type="button" data-page="${item}" ${item === state.page ? 'aria-current="page"' : ""} aria-label="Page ${item}">${item}</button>`).join("");
  nav.innerHTML = `
    <button class="page-button is-arrow prev" type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""} aria-label="Previous page">${icon("arrow")}</button>
    ${numbered}
    <button class="page-button is-arrow" type="button" data-page="${state.page + 1}" ${state.page === pageCount ? "disabled" : ""} aria-label="Next page">${icon("arrow")}</button>`;
}

const FILTERS = [
  { key: "cluster", label: "Sector cluster", reset: () => { state.filters.cluster = "all"; $("cluster-filter").value = "all"; } },
  { key: "score", label: "Signal strength", reset: () => { state.filters.minScore = 0; $("score-filter").value = "0"; } },
  { key: "signals", label: "Must-have signals", reset: () => { state.filters.signals = []; populateSectorFilters(); } },
  { key: "young", label: "Young companies only", add: () => { state.filters.youngOnly = true; $("young-filter").checked = true; }, reset: () => { state.filters.youngOnly = false; $("young-filter").checked = false; } },
  { key: "sector", label: "Industry", reset: () => { state.filters.sector = "all"; $("sector-filter").value = "all"; } },
  { key: "nj", label: "NJ evidence", reset: () => { state.filters.nj = "all"; $("nj-filter").value = "all"; } },
  { key: "record", label: "Record type", reset: () => { state.filters.recordType = "all"; $("record-filter").value = "all"; } },
  { key: "startup", label: "Include non-startups", add: () => { state.filters.hideNonStartups = false; $("startup-filter").checked = false; }, reset: () => { state.filters.hideNonStartups = true; $("startup-filter").checked = true; } },
];

function renderFilterSlots() {
  const shown = state.shownFilters;
  document.querySelectorAll("[data-filter-slot]").forEach((slot) => { slot.hidden = !shown.includes(slot.dataset.filterSlot); });
  $("active-filters").hidden = !shown.length;
  const remaining = FILTERS.filter((filter) => !shown.includes(filter.key));
  $("add-filter").hidden = !remaining.length;
  $("add-filter-menu").innerHTML = remaining.map((filter) => `<button type="button" data-add-filter="${filter.key}">${escapeHTML(filter.label)}</button>`).join("");
}

function addFilter(key) {
  const filter = FILTERS.find((item) => item.key === key);
  if (!filter || state.shownFilters.includes(key)) return;
  state.shownFilters = [...state.shownFilters, key];
  filter.add?.();
  $("add-filter").open = false;
  state.page = 1;
  renderFilterSlots();
  renderDirectory();
  document.querySelector(`[data-filter-slot="${key}"] select, [data-filter-slot="${key}"] button.signal-chip`)?.focus();
}

function removeFilter(key) {
  FILTERS.find((item) => item.key === key)?.reset();
  state.shownFilters = state.shownFilters.filter((item) => item !== key);
  state.page = 1;
  renderFilterSlots();
  renderDirectory();
}

function clearFilters() {
  state.shownFilters = [];
  renderFilterSlots();
  state.filters = { ...state.filters, query: "", hideNonStartups: true, nj: "all", sector: "all", recordType: "all", cluster: "all", minScore: 0, youngOnly: false, signals: [], sort: "signal" };
  state.page = 1;
  $("catalog-search").value = "";
  $("startup-filter").checked = true;
  $("young-filter").checked = false;
  $("nj-filter").value = "all";
  $("sector-filter").value = "all";
  $("record-filter").value = "all";
  $("cluster-filter").value = "all";
  $("score-filter").value = "0";
  $("sort-filter").value = "signal";
  populateSectorFilters();
  renderDirectory();
}

function setView(view, { scroll = true } = {}) {
  state.view = ["shortlist", "sectors", "scoring"].includes(view) ? view : "directory";
  state.page = 1;
  $("directory-section").hidden = ["sectors", "scoring"].includes(state.view);
  $("sectors-section").hidden = state.view !== "sectors";
  $("scoring-section").hidden = state.view !== "scoring";
  history.replaceState(null, "", state.view === "directory" ? location.pathname : `#${state.view}`);
  document.querySelectorAll("[data-view]").forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (state.view === "shortlist") {
    $("breadcrumb-current").textContent = "Shortlist";
    $("page-title").innerHTML = "Your saved companies,<br><em>ready for a closer look.</em>";
    $("page-description").textContent = "Your saved companies and notes. Compare up to three side by side.";
    $("directory-title").textContent = "Shortlisted companies";
  } else if (state.view === "scoring") {
    $("breadcrumb-current").textContent = "How scoring works";
    $("page-title").innerHTML = "How we rank<br><em>New Jersey startups.</em>";
    $("page-description").textContent = "Simple points for public signals, with every point shown. Here is exactly how a company and a sector earn their scores.";
  } else if (state.view === "sectors") {
    $("breadcrumb-current").textContent = "Sectors & map";
    $("page-title").innerHTML = "Where New Jersey<br><em>is gaining traction.</em>";
    $("page-description").textContent = "Which sectors and regions show the strongest signals, and how each ranking is built.";
  } else {
    $("breadcrumb-current").textContent = "Company directory";
    $("page-title").innerHTML = "New Jersey startups,<br><em>with the receipts.</em>";
    $("page-description").textContent = "Find promising NJ companies, see why they rank where they do and check every source.";
    $("directory-title").textContent = "Company directory";
  }
  closeSidebar();
  if (state.view === "scoring") {
    renderScoring();
    if (scroll) $("scoring-section").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  if (state.view === "sectors") {
    renderSectors();
    if (scroll) $("sectors-section").scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  renderDirectory();
  if (scroll) $("directory-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

function normalizeShortlist(payload) {
  const ids = uniqueStrings(payload?.ids);
  const rawNotes = asObject(payload?.notes);
  const notes = {};
  Object.entries(rawNotes).forEach(([id, note]) => {
    if (typeof note === "string") notes[String(id)] = note;
  });
  return { ids, notes };
}

function applyShortlist(payload) {
  state.shortlist = normalizeShortlist(payload);
  $("shortlist-count").textContent = formatNumber(state.shortlist.ids.length);
  renderDirectory();
  renderCompareState({ directory: false });
  if (state.detailCompany) renderCompanyDrawer(state.detailCompany, { fallback: state.detailFallback });
}

function enqueueShortlistOperation(operation) {
  const queued = state.shortlistQueue.then(operation, operation);
  state.shortlistQueue = queued.catch(() => undefined);
  return queued;
}

async function loadShortlist() {
  try {
    const payload = await enqueueShortlistOperation(async () => {
      const current = await apiFetch(API.shortlist);
      applyShortlist(current);
      return current;
    });
    return payload;
  } catch (error) {
    if (error.status !== 401) toast("The saved shortlist is temporarily unavailable.", "warning");
    return null;
  }
}

async function toggleShortlist(id, forcedSaved) {
  id = String(id);
  if (state.shortlistBusy.has(id)) return;
  const currentlySaved = state.shortlist.ids.map(String).includes(id);
  const saved = typeof forcedSaved === "boolean" ? forcedSaved : !currentlySaved;
  state.shortlistBusy.add(id);
  renderDirectory();
  try {
    await enqueueShortlistOperation(async () => {
      const body = { saved };
      if (Object.prototype.hasOwnProperty.call(state.shortlist.notes, id)) body.note = state.shortlist.notes[id];
      const payload = await apiFetch(`${API.shortlist}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) });
      state.shortlistBusy.delete(id);
      applyShortlist(payload);
    });
    const company = companyById(id);
    toast(`${company?.name || "Company"} ${saved ? "added to" : "removed from"} your shortlist.`);
  } catch (error) {
    state.shortlistBusy.delete(id);
    renderDirectory();
    if (error.status !== 401) toast(`Could not update the shortlist: ${error.message}`, "error");
  }
}

async function saveCompanyNote(id) {
  id = String(id);
  const textarea = $("company-drawer-content").querySelector("[data-company-note]");
  const button = $("company-drawer-content").querySelector("[data-save-note]");
  if (!textarea || !button) return;
  const note = textarea.value.trim();
  const wasSaved = state.shortlist.ids.map(String).includes(id);
  button.disabled = true;
  const previous = button.textContent;
  button.textContent = "Saving…";
  try {
    await enqueueShortlistOperation(async () => {
      const payload = await apiFetch(`${API.shortlist}/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ saved: true, note }),
      });
      applyShortlist(payload);
    });
    toast(wasSaved ? "Note saved." : "Note saved and company added to your shortlist.");
  } catch (error) {
    if (error.status !== 401) toast(`Could not save the note: ${error.message}`, "error");
  } finally {
    if (button.isConnected) {
      button.disabled = false;
      button.textContent = previous;
    }
  }
}

function updateCompany(company) {
  const index = state.catalog.findIndex((item) => String(item.id) === String(company.id));
  if (index >= 0) state.catalog[index] = company;
  else state.catalog.push(company);
}

function profilePillars(company) {
  return PILLARS.map(({ key, label }) => {
    const pillar = pillarFor(company, key);
    const summary = pillar.summary || (pillar.status === "missing" ? "No supported evidence has been attached to this pillar yet." : "Evidence is present, but no summary was provided.");
    const metrics = pillar.metrics.map((metric) => {
      const safeMetric = asObject(metric);
      return `<div class="metric"><span>${escapeHTML(safeMetric.label || "Metric")}</span><strong>${escapeHTML(safeMetric.value ?? "Unknown")}</strong>${safeMetric.detail ? `<small>${escapeHTML(safeMetric.detail)}</small>` : ""}</div>`;
    }).join("");
    const findings = pillar.findings.length ? `<ul class="finding-list">${pillar.findings.map((finding) => `<li>${escapeHTML(finding)}</li>`).join("")}</ul>` : "";
    const limits = pillar.limitations.length ? `<ul class="limit-list">${pillar.limitations.map((limit) => `<li>${escapeHTML(limit)}</li>`).join("")}</ul>` : "";
    return `
      <details class="pillar-card" ${pillar.status !== "missing" ? "open" : ""}>
        <summary><i class="${key}"></i><strong>${escapeHTML(label)}</strong><span class="status-badge ${pillar.status}">${escapeHTML(sentenceCase(pillar.status))}</span>${icon("chevron")}</summary>
        <div class="pillar-body"><p class="pillar-summary">${escapeHTML(summary)}</p>${metrics ? `<div class="metric-grid">${metrics}</div>` : ""}${findings}${limits}</div>
      </details>`;
  }).join("");
}

function profilePeople(company) {
  const people = asArray(company.people);
  if (!people.length) return "";
  const cards = people.map((person) => {
    const source = safeUrl(person?.source_url);
    return `<article class="person-card"><div class="person-initials" aria-hidden="true">${escapeHTML(initials(person?.name))}</div><div><strong>${escapeHTML(person?.name || "Name not reported")}</strong><span>${escapeHTML(person?.role || "Role not reported")}</span></div>${source ? `<a href="${escapeHTML(source)}" target="_blank" rel="noopener noreferrer" aria-label="Open source for ${escapeHTML(person?.name || "person")}">${icon("external")}</a>` : ""}</article>`;
  }).join("");
  return `<section class="profile-section"><div class="profile-section-head"><div><p class="section-number">People</p><h3>Named people &amp; reported roles</h3></div><span>${plural(people.length, "person", "people")}</span></div><div class="people-list">${cards}</div></section>`;
}

function profileSources(company) {
  const evidence = [...asArray(company.evidence)].sort((a, b) => String(b?.published_at || b?.observed_at || "").localeCompare(String(a?.published_at || a?.observed_at || "")));
  if (!evidence.length) {
    return `<section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Sources</p><h3>Traceable evidence</h3></div><span>0 sources</span></div><div class="global-limitations"><h4>No linked evidence yet</h4><ul><li>This record does not currently include a source URL and quote.</li></ul></div></section>`;
  }
  const rows = evidence.map((source) => {
    const url = safeUrl(source?.url);
    const pillar = PILLARS.find((item) => item.key === source?.pillar)?.label || sentenceCase(source?.pillar || "Evidence");
    const title = String(source?.title || (url ? new URL(url).hostname.replace(/^www\./, "") : "Untitled source"));
    return `<article class="evidence-source"><div class="source-meta"><span class="source-pillar">${escapeHTML(pillar)}</span>${source?.source_type ? `<span class="source-type">${escapeHTML(sentenceCase(source.source_type))}</span>` : ""}</div>${url ? `<a class="source-title" href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(title)} ${icon("external")}</a>` : `<div class="source-title">${escapeHTML(title)}</div>`}${source?.quote ? `<blockquote class="source-quote">${escapeHTML(source.quote)}</blockquote>` : ""}<div class="source-dates"><span><b>Published</b> ${escapeHTML(formatDate(source?.published_at))}</span><span><b>Observed</b> ${escapeHTML(formatDate(source?.observed_at))}</span></div></article>`;
  }).join("");
  return `<section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Sources</p><h3>Traceable evidence</h3></div><span>${plural(evidence.length, "evidence item")}</span></div><div class="source-list">${rows}</div></section>`;
}

function renderCompanyDrawer(company, { loading = false, fallback = false } = {}) {
  state.detailCompany = company;
  state.detailFallback = fallback;
  if (!company) {
    $("company-drawer-content").innerHTML = `<div class="drawer-loading"><div class="loading-lockup"><div class="spinner"></div><p>Loading company profile…</p></div></div>`;
    return;
  }
  const id = String(company.id);
  const saved = state.shortlist.ids.map(String).includes(id);
  const compared = state.compareIds.includes(id);
  const njSupported = company.nj_status === "supported";
  const likelyNonStartup = isLikelyNonStartup(company);
  const tags = uniqueStrings(company.tags);
  const limitations = uniqueStrings(company.limitations);
  const note = state.shortlist.notes[id] || "";
  const recordType = RECORD_LABELS[company.record_type] || sentenceCase(company.record_type || "Company record");
  const description = company.description || "No company description is attached to this record yet.";
  const reason = company.why_surfaced || "";

  $("company-drawer-content").innerHTML = `
    <section class="profile-hero">
      <div class="profile-kicker"><span class="badge ${njSupported ? "nj-supported" : "nj-unverified"}">${escapeHTML(njSupported ? "NJ evidence supported" : "NJ status unverified")}</span><span class="badge">${escapeHTML(recordType)}</span>${likelyNonStartup ? '<span class="badge likely-nonstartup">Likely non-startup entity</span>' : ""}</div>
      <div class="profile-title-row"><div class="profile-avatar" aria-hidden="true">${escapeHTML(initials(company.name))}</div><div><h2 id="drawer-title">${escapeHTML(company.name || "Unnamed company")}</h2><p>${escapeHTML(company.sector || "Sector not reported")} · ${escapeHTML(company.location || "Location not reported")}</p></div></div>
      <p class="profile-description">${escapeHTML(description)}</p>
      ${reason ? `<p class="profile-reason"><strong>Why it surfaced:</strong> ${escapeHTML(reason)}</p>` : ""}
      ${tags.length ? `<div class="profile-tags">${tags.map((tag) => `<span class="profile-tag">${escapeHTML(tag)}</span>`).join("")}</div>` : ""}
      <div class="profile-actions"><button class="button ${saved ? "button-outline" : "button-dark"}" type="button" data-toggle-save="${escapeHTML(id)}">${icon("bookmark")} ${saved ? "Remove from shortlist" : "Add to shortlist"}</button><button class="button ${compared ? "button-accent" : "button-outline"}" type="button" data-toggle-compare="${escapeHTML(id)}">${icon("compare")} ${compared ? "Added to comparison" : "Add to comparison"}</button></div>
      ${loading ? `<div class="profile-fallback"><div class="spinner" aria-hidden="true"></div><span>Checking the latest profile…</span></div>` : fallback ? `<div class="profile-fallback">${icon("warning")}<span>The latest profile could not load. This is the catalog snapshot.</span></div>` : ""}
    </section>
    <div class="profile-stat-row"><div class="profile-stat"><strong>${signalScore(company).total}/100</strong><span>Signal score</span></div><div class="profile-stat"><strong>${coverageCount(company)}/4</strong><span>Evidence pillars</span></div><div class="profile-stat"><strong>${formatNumber(company.source_count)}</strong><span>Unique sources</span></div><div class="profile-stat"><strong>${escapeHTML(formatDate(company.updated_at, { month: "short", day: "numeric", year: "numeric" }))}</strong><span>Record updated</span></div></div>
    ${scoreBreakdown(company)}
    <section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Evidence map</p><h3>Four research pillars</h3></div><span>Coverage is not a score</span></div><div class="pillar-list">${profilePillars(company)}</div></section>
    ${profilePeople(company)}
    ${profileSources(company)}
    <section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Your notes</p><h3>Keep the context close</h3></div><span>Saved on this server</span></div><div class="note-card"><textarea data-company-note maxlength="4000" placeholder="Add a question, follow-up or decision note…">${escapeHTML(note)}</textarea><div class="note-actions"><span>${saved ? "Attached to your shortlist" : "Saving a note also adds this company to your shortlist"}</span><button class="button button-dark" type="button" data-save-note="${escapeHTML(id)}">Save note</button></div></div></section>
    ${limitations.length ? `<section class="profile-section"><div class="profile-section-head"><div><p class="section-number">Limits</p><h3>What remains unknown</h3></div></div><div class="global-limitations"><h4>Read before drawing a conclusion</h4><ul>${limitations.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul></div></section>` : ""}`;
}

async function openCompany(id, trigger = document.activeElement) {
  id = String(id);
  const generation = ++state.detailGeneration;
  const catalogCompany = companyById(id);
  renderCompanyDrawer(catalogCompany, { loading: Boolean(catalogCompany) });
  openLayer($("company-layer"), trigger);
  try {
    const company = await apiFetch(`/api/companies/${encodeURIComponent(id)}`);
    updateCompany(company);
    if (generation !== state.detailGeneration || String(company.id) !== id || $("company-layer").hidden) return;
    renderCompanyDrawer(company);
    renderDirectory();
  } catch (error) {
    if (generation !== state.detailGeneration || $("company-layer").hidden) return;
    if (error.status === 401) return;
    if (catalogCompany) {
      renderCompanyDrawer(catalogCompany, { fallback: true });
      toast("The latest profile could not load. Showing the catalog snapshot.", "warning");
    } else {
      $("company-drawer-content").innerHTML = `<div class="catalog-error"><span>${icon("warning")}</span><div><h3>Profile unavailable</h3><p>${escapeHTML(error.message)}</p></div></div>`;
    }
  }
}

function renderCompareState({ directory = true } = {}) {
  const validIds = state.compareIds.filter((id) => companyById(id));
  if (validIds.length !== state.compareIds.length) state.compareIds = validIds;
  const count = state.compareIds.length;
  $("compare-count").textContent = count;
  $("mobile-compare-count").textContent = count;
  $("mobile-compare-count").hidden = !count;
  $("compare-button-count").textContent = count;
  $("compare-tray").hidden = !count;
  $("open-comparison").disabled = count < 2;
  $("compare-tray-help").textContent = count < 2 ? "Add one more to compare" : `${count} of 3 selected`;
  $("compare-chips").innerHTML = state.compareIds.map((id) => {
    const company = companyById(id);
    return `<div class="compare-chip"><span class="compare-avatar" aria-hidden="true">${escapeHTML(initials(company.name))}</span><span>${escapeHTML(company.name)}</span><button type="button" data-remove-compare="${escapeHTML(id)}" aria-label="Remove ${escapeHTML(company.name)} from comparison">${icon("close")}</button></div>`;
  }).join("");
  if (directory) renderDirectory();
  if (!$("compare-layer").hidden) renderComparison();
}

function toggleCompare(id) {
  id = String(id);
  const index = state.compareIds.indexOf(id);
  if (index >= 0) {
    state.compareIds.splice(index, 1);
  } else if (state.compareIds.length >= 3) {
    toast("Comparison holds three companies. Remove one before adding another.", "warning");
    return;
  } else {
    state.compareIds.push(id);
  }
  renderCompareState();
  if (state.detailCompany && String(state.detailCompany.id) === id) renderCompanyDrawer(state.detailCompany, { fallback: state.detailFallback });
}

function renderComparison() {
  const companies = state.compareIds.map(companyById).filter(Boolean);
  const container = $("comparison-content");
  if (companies.length < 2) {
    container.innerHTML = `<div class="compare-empty"><div>${icon("compare")}<h3>Choose at least two companies.</h3><p>Add records from the directory. You can compare up to three at once.</p><button class="button button-dark" type="button" data-action="browse-directory">Browse directory</button></div></div>`;
    return;
  }
  const headers = companies.map((company) => `<div class="compare-cell compare-company"><span class="compare-avatar" aria-hidden="true">${escapeHTML(initials(company.name))}</span><h3>${escapeHTML(company.name)}</h3><p>${escapeHTML(company.sector || "Sector not reported")}</p><button class="remove-comparison" type="button" data-remove-compare="${escapeHTML(company.id)}" aria-label="Remove ${escapeHTML(company.name)}">${icon("close")}</button></div>`).join("");
  const overview = companies.map((company) => `<div class="compare-cell"><span class="badge ${company.nj_status === "supported" ? "nj-supported" : "nj-unverified"}">${escapeHTML(company.nj_status === "supported" ? "NJ supported" : "NJ unverified")}</span><p>${escapeHTML(RECORD_LABELS[company.record_type] || sentenceCase(company.record_type || "Company record"))}</p><div class="compare-mini-metrics"><span>${coverageCount(company)}/4 pillars</span><span>${plural(finiteNumber(company.source_count), "source")}</span></div></div>`).join("");
  const scoreCells = companies.map((company) => {
    const score = signalScore(company);
    const detected = score.components.filter((item) => item?.detected).map((item) => `<span>${escapeHTML(item.label)}: ${formatNumber(item.points)}/${escapeHTML(item.max)}</span>`).join("");
    return `<div class="compare-cell">${scoreBadge(company)}<div class="compare-mini-metrics">${detected || "<span>No signals detected</span>"}</div></div>`;
  }).join("");
  const scoreRow = `<div class="compare-row"><div class="compare-label">Signal score</div>${scoreCells}</div>`;
  const pillarRows = PILLARS.map(({ key, label }) => {
    const cells = companies.map((company) => {
      const pillar = pillarFor(company, key);
      const summary = pillar.summary || (pillar.status === "missing" ? "No supported evidence attached." : "Summary not reported.");
      const metrics = pillar.metrics.slice(0, 3).map((metric) => `<span>${escapeHTML(metric?.label || "Metric")}: ${escapeHTML(metric?.value ?? "Unknown")}</span>`).join("");
      return `<div class="compare-cell"><span class="status-badge ${pillar.status}">${escapeHTML(sentenceCase(pillar.status))}</span><p>${escapeHTML(summary)}</p>${metrics ? `<div class="compare-mini-metrics">${metrics}</div>` : ""}</div>`;
    }).join("");
    return `<div class="compare-row"><div class="compare-label">${escapeHTML(label)}</div>${cells}</div>`;
  }).join("");
  container.innerHTML = `<div class="compare-table" style="--compare-columns:${companies.length}"><div class="compare-row"><div class="compare-label">Company</div>${headers}</div><div class="compare-row"><div class="compare-label">Record</div>${overview}</div>${scoreRow}${pillarRows}</div>`;
}

function openComparison(trigger = document.activeElement) {
  renderComparison();
  openLayer($("compare-layer"), trigger);
}

function clusterColor(key) {
  return CLUSTER_COLORS[key] || CLUSTER_COLORS.other;
}

function formatUsdShort(value) {
  const amount = finiteNumber(value);
  if (amount >= 1e9) return `$${(amount / 1e9).toFixed(1)}B`;
  if (amount >= 1e6) return `$${(amount / 1e6).toFixed(1)}M`;
  if (amount >= 1e3) return `$${(amount / 1e3).toFixed(0)}K`;
  return `$${formatNumber(amount)}`;
}

function formatPct(value) {
  if (value == null || !Number.isFinite(Number(value))) return "No prior window";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(0)}%`;
}

function niceMax(value) {
  if (value <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  return [1, 2, 2.5, 5, 10].map((step) => step * power).find((candidate) => candidate >= value);
}

function tipAttr(lines) {
  return `data-tip="${escapeHTML(JSON.stringify(lines))}" tabindex="0"`;
}

function rankedClusters() {
  return asArray(state.sectorView?.clusters).filter((cluster) => cluster?.ranked);
}

function renderSectors() {
  const view = state.sectorView;
  const ranked = rankedClusters();
  $("sectors-count").textContent = view ? formatNumber(ranked.length) : "—";
  if (state.view !== "sectors") return;
  if (!view) {
    $("sectors-lead").textContent = state.catalogLoading ? "Loading sector signals…" : "Sector signals are not available in this catalog snapshot.";
    ["sector-table", "cluster-chart", "region-map", "trend-chart", "trend-table", "sector-method"].forEach((id) => { $(id).innerHTML = ""; });
    return;
  }
  const leader = ranked[0];
  $("sectors-lead").innerHTML = `<strong>${formatNumber(view.startup_like_companies)}</strong> startup-like companies grouped into <strong>${formatNumber(ranked.length)}</strong> ranked sector clusters, using SEC Form D filings through <strong>${escapeHTML(formatDate(view.window_end))}</strong>.${leader ? ` <strong>${escapeHTML(leader.label)}</strong> currently shows the strongest combined signal.` : ""}`;
  renderSectorTable();
  renderClusterChart();
  renderRegionMap();
  renderTrendChart();
  $("sector-method").innerHTML = asArray(view.method).map((line) => `<li>${escapeHTML(line)}</li>`).join("");
}

function renderSectorTable() {
  const clusters = asArray(state.sectorView?.clusters);
  const body = clusters.map((cluster) => {
    const score = asObject(cluster.score);
    const open = state.selectedSector === cluster.key;
    const top = asArray(cluster.top).slice(0, 3).map((company) => `<button type="button" class="link-button" data-open-company="${escapeHTML(company.id)}">${escapeHTML(company.name)} <b>${finiteNumber(company.score)}</b></button>`).join("");
    const components = asArray(score.components).map((item) => {
      const width = Math.max(0, Math.min(100, (finiteNumber(item.points) / finiteNumber(item.max, 1)) * 100));
      return `<div class="score-row"><div class="score-row-head"><span>${escapeHTML(item.label)}</span><strong>${formatNumber(item.points)} / ${escapeHTML(item.max)}</strong></div><div class="score-track" aria-hidden="true"><span style="width:${width}%"></span></div><small>${escapeHTML(item.detail)}</small></div>`;
    }).join("");
    const momentumClass = cluster.momentum_pct == null ? "" : cluster.momentum_pct >= 0 ? "is-up" : "is-down";
    return `
      <tr class="${open ? "is-open" : ""}">
        <td class="num">${cluster.rank ?? "—"}</td>
        <td><button type="button" class="sector-name" data-sector-row="${escapeHTML(cluster.key)}" aria-expanded="${open}"><i style="background:${clusterColor(cluster.key)}"></i>${escapeHTML(cluster.label)}${icon("chevron")}</button>${cluster.ranked ? "" : '<small class="unranked-note">Not ranked: mixed SEC “Other” industry</small>'}</td>
        <td><span class="score-inline tier-${escapeHTML(score.tier || "low")}"><strong>${finiteNumber(score.total)}</strong><span class="score-track" aria-hidden="true"><span style="width:${finiteNumber(score.total)}%"></span></span></span></td>
        <td class="num">${formatNumber(cluster.companies)}</td>
        <td class="num">${formatNumber(cluster.elevated_companies)}</td>
        <td class="num">${formatNumber(cluster.rounds_recent)}</td>
        <td class="num momentum ${momentumClass}">${escapeHTML(formatPct(cluster.momentum_pct))}</td>
        <td class="top-companies">${top || "—"}</td>
        <td><button type="button" class="button button-quiet small" data-view-cluster="${escapeHTML(cluster.key)}">Companies ${icon("arrow")}</button></td>
      </tr>
      ${open ? `<tr class="sector-detail"><td></td><td colspan="8"><div class="score-breakdown">${components}</div><p class="score-note">Includes SEC industries: ${escapeHTML(asArray(cluster.sectors).join(", "))}.</p></td></tr>` : ""}`;
  }).join("");
  $("sector-table").innerHTML = `<thead><tr><th class="num">Rank</th><th>Cluster</th><th>Sector score</th><th class="num">Companies</th><th class="num">Score 35+</th><th class="num">Rounds, 24 mo</th><th class="num">Momentum</th><th>Top companies</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${body}</tbody>`;
}

function renderClusterChart() {
  const clusters = rankedClusters();
  const container = $("cluster-chart");
  if (!clusters.length) {
    container.innerHTML = '<p class="viz-empty">No ranked clusters.</p>';
    return;
  }
  const width = 560;
  const height = 380;
  const margin = { top: 24, right: 28, bottom: 52, left: 52 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const extent = Math.max(50, ...clusters.map((cluster) => Math.abs(finiteNumber(cluster.momentum_pct))));
  const xMax = Math.ceil(extent / 25) * 25;
  const yMax = Math.min(100, Math.ceil((Math.max(...clusters.map((cluster) => finiteNumber(cluster.score?.total))) + 10) / 20) * 20);
  const maxCompanies = Math.max(...clusters.map((cluster) => finiteNumber(cluster.companies, 1)));
  const x = (value) => margin.left + ((value + xMax) / (2 * xMax)) * plotW;
  const y = (value) => margin.top + plotH - (value / yMax) * plotH;
  const radius = (count) => 7 + 21 * Math.sqrt(finiteNumber(count) / maxCompanies);

  const yTicks = Array.from({ length: yMax / 20 + 1 }, (_, index) => index * 20);
  const xTicks = [-xMax, -xMax / 2, 0, xMax / 2, xMax];
  const grid = yTicks.map((tick) => `<line class="grid" x1="${margin.left}" x2="${margin.left + plotW}" y1="${y(tick)}" y2="${y(tick)}"/><text class="tick" x="${margin.left - 10}" y="${y(tick) + 4}" text-anchor="end">${tick}</text>`).join("")
    + xTicks.map((tick) => `<text class="tick" x="${x(tick)}" y="${margin.top + plotH + 20}" text-anchor="middle">${tick > 0 ? "+" : ""}${tick}%</text>`).join("");
  const sorted = [...clusters].sort((a, b) => finiteNumber(b.companies) - finiteNumber(a.companies));
  const bubbles = sorted.map((cluster) => {
    const cx = x(Math.max(-xMax, Math.min(xMax, finiteNumber(cluster.momentum_pct))));
    const cy = y(finiteNumber(cluster.score?.total));
    const r = radius(cluster.companies);
    const labelRight = cx < margin.left + plotW * 0.7;
    const tip = [cluster.label, `Sector score ${finiteNumber(cluster.score?.total)}/100 (rank ${cluster.rank})`, `Momentum ${formatPct(cluster.momentum_pct)} · ${formatNumber(cluster.rounds_recent)} rounds in 24 mo`, `${formatNumber(cluster.companies)} companies · ${formatNumber(cluster.elevated_companies)} score 35+`];
    return `<g class="bubble" ${tipAttr(tip)} data-view-cluster="${escapeHTML(cluster.key)}" role="button" aria-label="${escapeHTML(tip.join(". "))}"><circle cx="${cx}" cy="${cy}" r="${r + 10}" fill="transparent"/><circle class="bubble-mark" cx="${cx}" cy="${cy}" r="${r}" fill="${clusterColor(cluster.key)}"/><text class="bubble-label" x="${labelRight ? cx + r + 6 : cx - r - 6}" y="${cy + 4}" text-anchor="${labelRight ? "start" : "end"}">${escapeHTML(cluster.label)}</text></g>`;
  }).join("");
  container.innerHTML = `
    <svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sector clusters plotted by funding momentum and sector score">
      ${grid}
      <line class="baseline" x1="${x(0)}" x2="${x(0)}" y1="${margin.top}" y2="${margin.top + plotH}"/>
      <line class="baseline" x1="${margin.left}" x2="${margin.left + plotW}" y1="${margin.top + plotH}" y2="${margin.top + plotH}"/>
      <text class="quadrant" x="${margin.left + plotW - 4}" y="${margin.top + 12}" text-anchor="end">Accelerating ↗</text>
      <text class="quadrant" x="${margin.left + 4}" y="${margin.top + 12}">↖ Cooling</text>
      ${bubbles}
      <text class="axis-title" x="${margin.left + plotW / 2}" y="${height - 8}" text-anchor="middle">Funding momentum: rounds in latest 24 months vs prior 24</text>
      <text class="axis-title" transform="translate(14 ${margin.top + plotH / 2}) rotate(-90)" text-anchor="middle">Sector score</text>
    </svg>`;
}

function renderRegionMap() {
  const view = state.sectorView;
  const regions = asArray(view?.regions);
  const clusterKey = state.regionCluster;
  const clusterLabel = clusterKey === "all" ? "all clusters" : asArray(view?.clusters).find((cluster) => cluster.key === clusterKey)?.label || clusterKey;
  const value = (region) => finiteNumber(clusterKey === "all" ? region.companies : asObject(region.by_cluster)[clusterKey]);
  const max = Math.max(1, ...regions.map(value));
  $("region-caption").textContent = `Startup-like companies with a NJ Form D address · ${clusterLabel}`;
  const tiles = regions.map((region) => {
    const count = value(region);
    const step = count ? Math.min(SEQUENTIAL.length - 1, Math.floor((count / max) * (SEQUENTIAL.length - 1) + 0.0001)) : -1;
    const fill = step >= 0 ? SEQUENTIAL[step] : "var(--paper)";
    const dark = step >= 3;
    const [col, row, span] = asArray(region.grid);
    const share = clusterKey === "all" ? `${formatNumber(region.elevated_companies)} score 35+` : `${Math.round((count / Math.max(1, finiteNumber(region.companies))) * 100)}% of region`;
    const tip = [region.label, `${formatNumber(count)} companies (${clusterLabel})`, `${formatNumber(region.elevated_companies)} score 35+ across all clusters`, `${formatUsdShort(region.raised_recent)} raised in latest 24 months`, `ZIP areas ${asArray(region.zip3).join(", ")}`];
    return `<div class="region-tile${dark ? " is-dark" : ""}" style="grid-column:${col};grid-row:${row} / span ${span};background:${fill}" ${tipAttr(tip)} aria-label="${escapeHTML(tip.join(". "))}"><span>${escapeHTML(region.label)}</span><strong>${formatNumber(count)}</strong><small>${escapeHTML(share)}</small></div>`;
  }).join("");
  const legend = SEQUENTIAL.map((color) => `<i style="background:${color}"></i>`).join("");
  $("region-map").innerHTML = `<div class="region-grid">${tiles}</div><div class="region-legend"><span>Fewer</span><span class="ramp">${legend}</span><span>More (max ${formatNumber(max)})</span></div><p class="viz-footnote">Schematic layout of USPS ZIP regions, north at top. Not to scale.</p>`;
}

function renderTrendChart() {
  const view = state.sectorView;
  const clusters = rankedClusters();
  const partial = view?.partial_year || "";
  const allYears = asArray(view?.years);
  const years = allYears.filter((year) => year !== partial);
  const metric = state.trendMetric;
  const field = metric === "amount" ? "amount_by_year" : "rounds_by_year";
  const fmt = metric === "amount" ? formatUsdShort : formatNumber;
  document.querySelectorAll("[data-trend-metric]").forEach((button) => button.classList.toggle("is-active", button.dataset.trendMetric === metric));
  $("trend-caption").textContent = `SEC Form D ${metric === "amount" ? "amount sold" : "rounds filed"} per year, startup-like companies${partial ? ` · ${partial} is partial (through ${formatDate(view.window_end)}) and shown only in the table` : ""}`;
  const container = $("trend-chart");
  if (years.length < 2 || !clusters.length) {
    container.innerHTML = '<p class="viz-empty">Not enough dated filings for a trend.</p>';
    $("trend-table").innerHTML = "";
    return;
  }
  const width = 1000;
  const height = 300;
  const margin = { top: 20, right: 24, bottom: 36, left: 64 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const valueOf = (cluster, year) => finiteNumber(asObject(cluster[field])[year]);
  const yMax = niceMax(Math.max(...clusters.flatMap((cluster) => years.map((year) => valueOf(cluster, year)))));
  const x = (index) => margin.left + (index / (years.length - 1)) * plotW;
  const y = (value) => margin.top + plotH - (value / yMax) * plotH;
  const ticks = Array.from({ length: 5 }, (_, index) => (yMax / 4) * index);
  const grid = ticks.map((tick) => `<line class="grid" x1="${margin.left}" x2="${margin.left + plotW}" y1="${y(tick)}" y2="${y(tick)}"/><text class="tick" x="${margin.left - 10}" y="${y(tick) + 4}" text-anchor="end">${escapeHTML(fmt(tick))}</text>`).join("")
    + years.map((year, index) => `<text class="tick" x="${x(index)}" y="${margin.top + plotH + 22}" text-anchor="middle">${escapeHTML(year)}</text>`).join("");
  const lines = clusters.map((cluster) => {
    const points = years.map((year, index) => [x(index), y(valueOf(cluster, year))]);
    const path = points.map(([px, py], index) => `${index ? "L" : "M"}${px.toFixed(1)} ${py.toFixed(1)}`).join(" ");
    const markers = points.map(([px, py]) => `<circle class="line-marker" cx="${px}" cy="${py}" r="4" fill="${clusterColor(cluster.key)}"/>`).join("");
    return `<g><path class="line" d="${path}" stroke="${clusterColor(cluster.key)}"/>${markers}</g>`;
  }).join("");
  const columnWidth = plotW / (years.length - 1);
  const hover = years.map((year, index) => {
    const rows = [...clusters].sort((a, b) => valueOf(b, year) - valueOf(a, year)).map((cluster) => `${cluster.label}: ${fmt(valueOf(cluster, year))}`);
    return `<g class="crosshair-zone" ${tipAttr([year, ...rows])} aria-label="${escapeHTML([year, ...rows].join(". "))}"><rect x="${x(index) - columnWidth / 2}" y="${margin.top}" width="${columnWidth}" height="${plotH}" fill="transparent"/><line class="crosshair" x1="${x(index)}" x2="${x(index)}" y1="${margin.top}" y2="${margin.top + plotH}"/></g>`;
  }).join("");
  const legend = clusters.map((cluster) => `<span><i style="background:${clusterColor(cluster.key)}"></i>${escapeHTML(cluster.label)}</span>`).join("");
  container.innerHTML = `<div class="chart-legend">${legend}</div><svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Form D ${metric} per year by sector cluster">${grid}<line class="baseline" x1="${margin.left}" x2="${margin.left + plotW}" y1="${y(0)}" y2="${y(0)}"/>${lines}${hover}</svg>`;

  const head = allYears.map((year) => `<th class="num">${escapeHTML(year)}${year === partial ? "*" : ""}</th>`).join("");
  const rows = asArray(view?.clusters).map((cluster) => `<tr><td><i class="dot" style="background:${clusterColor(cluster.key)}"></i>${escapeHTML(cluster.label)}</td>${allYears.map((year) => `<td class="num">${escapeHTML(fmt(valueOf(cluster, year)))}</td>`).join("")}</tr>`).join("");
  $("trend-table").innerHTML = `<table class="sector-table compact"><thead><tr><th>Cluster</th>${head}</tr></thead><tbody>${rows}</tbody></table>${partial ? `<p class="viz-footnote">* ${escapeHTML(partial)} covers filings through ${escapeHTML(formatDate(view.window_end))} only.</p>` : ""}`;
}

function renderScoring() {
  if (state.view !== "scoring") return;
  $("weight-bar").innerHTML = SIGNAL_GUIDE.map((signal) => `<span style="flex:${signal.max}" title="${escapeHTML(signal.label)}: ${signal.max} points"><b>${signal.max}</b><small>${escapeHTML(signal.label)}</small></span>`).join("");
  $("signal-table").innerHTML = `<thead><tr><th>Signal</th><th class="num">Max points</th><th>What earns full points</th><th>Where the data comes from</th></tr></thead><tbody>${SIGNAL_GUIDE.map((signal) => `<tr><td><strong>${escapeHTML(signal.label)}</strong></td><td class="num">${signal.max}</td><td>${escapeHTML(signal.full)}</td><td>${escapeHTML(signal.source)}</td></tr>`).join("")}<tr class="total-row"><td><strong>Total</strong></td><td class="num"><strong>100</strong></td><td colspan="2">Partial evidence earns partial points on a sliding scale.</td></tr></tbody>`;

  const companies = state.catalog.filter((company) => !isLikelyNonStartup(company));
  const counts = Object.fromEntries(TIER_GUIDE.map((tier) => [tier.key, 0]));
  companies.forEach((company) => { const tier = signalScore(company).tier || "low"; if (tier in counts) counts[tier] += 1; });
  $("tier-list").innerHTML = TIER_GUIDE.map((tier) => `<div class="tier-item"><span class="score-badge tier-${tier.key}"><strong>${tier.range}</strong><small>${escapeHTML(tier.label)}</small></span><p>${escapeHTML(tier.text)}</p><span class="tier-count">${formatNumber(counts[tier.key])} companies</span></div>`).join("");

  const top = [...companies].sort((a, b) => signalScore(b).total - signalScore(a).total)[0];
  const open = $("example-open");
  if (top) {
    $("example-caption").textContent = `${top.name} scores ${signalScore(top).total}/100. Here is every point, and why.`;
    $("scoring-example").innerHTML = scoreBreakdown(top);
    open.hidden = false;
    open.dataset.openCompany = String(top.id);
  } else {
    $("example-caption").textContent = state.catalogLoading ? "Loading…" : "No companies loaded.";
    $("scoring-example").innerHTML = "";
    open.hidden = true;
  }

  const leader = rankedClusters()[0];
  const parts = asArray(leader?.score?.components);
  $("sector-example").textContent = leader
    ? `Right now ${leader.label} ranks #1 with ${finiteNumber(leader.score.total)}/100: ${parts.map((part) => `${part.label.toLowerCase()} ${formatNumber(part.points)}/${part.max}`).join(", ")}. See the full ranking on the Sectors & map tab.`
    : "";
}

function showTip(target) {
  const tooltip = $("viz-tooltip");
  let lines;
  try {
    lines = JSON.parse(target.dataset.tip || "[]");
  } catch {
    return;
  }
  tooltip.innerHTML = lines.map((line, index) => index ? `<span>${escapeHTML(line)}</span>` : `<strong>${escapeHTML(line)}</strong>`).join("");
  tooltip.hidden = false;
  const box = target.getBoundingClientRect();
  const tipBox = tooltip.getBoundingClientRect();
  let left = box.left + box.width / 2 - tipBox.width / 2;
  left = Math.max(8, Math.min(window.innerWidth - tipBox.width - 8, left));
  let top = box.top - tipBox.height - 10;
  if (top < 8) top = box.bottom + 10;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function hideTip() {
  $("viz-tooltip").hidden = true;
}

function viewCluster(key) {
  state.filters.cluster = key;
  state.filters.sort = "signal";
  $("sort-filter").value = "signal";
  if (!state.shownFilters.includes("cluster")) state.shownFilters = [...state.shownFilters, "cluster"];
  populateSectorFilters();
  renderFilterSlots();
  setView("directory");
}

function downloadBlob(contents, type, filename) {
  const url = URL.createObjectURL(new Blob([contents], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function csvCell(value) {
  let text = value == null ? "" : String(value);
  if (/^\s*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function exportEvidence(format) {
  const companies = getFilteredCompanies();
  if (!companies.length) {
    toast("There are no matching records to export.", "warning");
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  if (format === "json") {
    const ids = new Set(state.shortlist.ids.map(String));
    const payload = {
      export: {
        product: "Garden State · Startup intelligence",
        generated_at: new Date().toISOString(),
        snapshot_date: state.snapshotDate || null,
        view: state.view,
        company_count: companies.length,
        filters: { ...state.filters, perPage: undefined },
        note: "Signal scores rank observed public signals with a visible breakdown. Neither the score nor evidence coverage predicts success or constitutes investment advice.",
      },
      companies: companies.map((company) => ({
        ...company,
        shortlist: ids.has(String(company.id)),
        note: state.shortlist.notes[String(company.id)] || "",
      })),
    };
    downloadBlob(JSON.stringify(payload, null, 2), "application/json;charset=utf-8", `garden-state-evidence-${today}.json`);
  } else {
    const headers = ["company_id", "company_name", "sector", "cluster", "location", "nj_status", "record_type", "signal_score", "signal_tier", "signals_detected", "pillar", "source_title", "source_url", "quote", "published_at", "observed_at", "source_type"];
    const rows = [headers];
    companies.forEach((company) => {
      const score = signalScore(company);
      const base = [company.id, company.name, company.sector, company.cluster, company.location, company.nj_status, company.record_type, score.total, score.tier_label, score.signals.join("; ")];
      const evidence = asArray(company.evidence);
      if (!evidence.length) {
        rows.push([...base, "", "", "", "", "", "", ""]);
        return;
      }
      evidence.forEach((source) => rows.push([...base, source?.pillar, source?.title, source?.url, source?.quote, source?.published_at, source?.observed_at, source?.source_type]));
    });
    const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
    downloadBlob(csv, "text/csv;charset=utf-8", `garden-state-evidence-${today}.csv`);
  }
  $("export-menu").open = false;
  toast(`${format.toUpperCase()} evidence export ready.`);
}

function researchIsLive() {
  const status = state.research.status;
  if (!status) return false;
  if (typeof status.live_available === "boolean") return status.live_available;
  return Boolean(status.gemini_configured && status.search_configured);
}

function renderResearchStatus() {
  const box = $("research-status");
  const dot = box.querySelector(".status-dot");
  const title = box.querySelector("strong");
  const copy = box.querySelector("p");
  const liveInput = document.querySelector('input[name="research-mode"][value="live"]');
  const sampleInput = document.querySelector('input[name="research-mode"][value="sample"]');
  const modeState = $("live-mode-state");

  dot.className = "status-dot";
  if (!state.research.status && !state.research.statusError) {
    dot.classList.add("is-loading");
    title.textContent = "Checking research service…";
    copy.textContent = "One moment.";
    modeState.textContent = "Checking";
    modeState.classList.remove("unavailable");
    return;
  }

  const live = researchIsLive();
  liveInput.disabled = !live;
  modeState.textContent = live ? "Ready" : "Unavailable";
  modeState.classList.toggle("unavailable", !live);
  if (!live && liveInput.checked) sampleInput.checked = true;

  if (state.research.statusError) {
    dot.classList.add("is-error");
    title.textContent = "Live status could not be checked";
    copy.textContent = "Saved public research may still be available. No live result will be substituted for it.";
  } else if (live) {
    title.textContent = "Live research is ready";
    copy.textContent = state.research.status.message || `Configured model: ${state.research.status.model || "server default"}.`;
  } else {
    dot.classList.add("is-error");
    title.textContent = "Live research is not configured";
    copy.textContent = state.research.status.message || "Choose saved public research to open the dated sample.";
  }
}

async function loadResearchStatus() {
  state.research.statusError = "";
  try {
    state.research.status = await apiFetch(API.researchStatus);
    populateSectorFilters();
  } catch (error) {
    if (error.status !== 401) state.research.statusError = error.message;
  } finally {
    renderResearchStatus();
  }
}

function researchStageIndex(job) {
  if (TERMINAL_RESEARCH_STATES.has(job?.status)) return 3;
  const stage = normalizedText(job?.stage);
  if (/connect|merge|rank|compare|final/.test(stage)) return 2;
  if (/verify|assess|read|resolve|evidence/.test(stage)) return 1;
  return 0;
}

function metricFromJob(job, keys) {
  const metrics = asObject(job?.metrics);
  for (const key of keys) {
    if (metrics[key] != null) return finiteNumber(metrics[key]);
  }
  return null;
}

function renderResearchJob(job) {
  state.research.job = job;
  const progress = $("research-progress");
  progress.hidden = false;
  const status = String(job?.status || "queued").toLowerCase();
  const terminal = TERMINAL_RESEARCH_STATES.has(status);
  const mode = job?.mode === "sample" ? "Saved public research" : "Live research";
  $("research-mode-label").textContent = mode;
  $("research-stage").textContent = job?.stage || (terminal ? sentenceCase(status) : "Preparing research");
  $("research-run-status").textContent = sentenceCase(status);
  $("research-run-status").className = `run-status ${escapeHTML(status)}`;
  const stages = [...$("stage-track").querySelectorAll("span")];
  const currentIndex = researchStageIndex(job);
  stages.forEach((stage, index) => {
    stage.classList.toggle("is-done", index < currentIndex || (terminal && index <= currentIndex));
    stage.classList.toggle("is-current", !terminal && index === currentIndex);
  });

  const cards = asArray(job?.cards);
  const reviewCards = asArray(job?.review_cards);
  const warnings = uniqueStrings(job?.warnings);
  const sourceCount = asArray(job?.sources).length || metricFromJob(job, ["sources", "source_count", "source_pages"]);
  const details = {
    queued: "The job is queued. Nothing has been claimed yet.",
    running: "Public sources are being checked and evidence gaps stay visible.",
    completed: "Research finished. The catalog is being refreshed with the saved result.",
    partial: "Research finished with gaps. Review the warnings before using the result.",
    failed: "The research run failed. No saved sample has been substituted for it.",
    interrupted: "The research run stopped before it finished. Any warnings below still apply.",
  };
  $("research-progress-detail").textContent = details[status] || "Research is in progress.";
  $("research-outcome").innerHTML = [
    [cards.length, "Profiles returned"],
    [reviewCards.length, "Need review"],
    [sourceCount ?? warnings.length, sourceCount == null ? "Warnings" : "Source pages"],
  ].map(([value, label]) => `<div class="outcome-stat"><strong>${formatNumber(value)}</strong><span>${escapeHTML(label)}</span></div>`).join("");

  const events = asArray(job?.events);
  $("research-events").innerHTML = events.length ? events.map((event) => `<li>${escapeHTML(typeof event === "string" ? event : event?.message || sentenceCase(event?.stage || "Activity recorded"))}</li>`).join("") : "<li>No activity has been reported yet.</li>";
  const reportedError = terminal ? String(job?.error || "").trim() : "";
  const terminalError = terminal && ["failed", "interrupted"].includes(status) && !reportedError ? `Research ended ${status}${job?.error_code ? ` (${job.error_code})` : ""}.` : "";
  const partialNotice = terminal && status === "partial" && !reportedError && !warnings.length ? "Research returned a partial result. Some evidence could not be completed." : "";
  const errorCode = terminal && job?.error_code && !reportedError.includes(String(job.error_code)) ? `Error code: ${job.error_code}` : "";
  const warningList = uniqueStrings([reportedError, terminalError, partialNotice, errorCode, ...warnings]);
  $("research-warnings").innerHTML = warningList.map((warning) => `<div class="research-warning">${icon("warning")}<span>${escapeHTML(warning)}</span></div>`).join("");

  const submit = $("research-submit");
  submit.disabled = state.research.busy;
  submit.querySelector("span").textContent = state.research.busy ? "Research in progress" : "Start another run";
}

async function finishResearchJob(job) {
  state.research.busy = false;
  renderResearchJob(job);
  const id = String(job?.id || "");
  let refreshAttempted = false;
  let refreshSucceeded = id ? state.research.refreshedJobs.has(id) : false;
  if (id && !state.research.refreshedJobs.has(id)) {
    refreshAttempted = true;
    try {
      await loadCatalog({ quiet: true });
      state.research.refreshedJobs.add(id);
      refreshSucceeded = true;
    } catch {
      // loadCatalog already reports refresh failures without hiding the terminal job.
    }
  }
  await loadResearchHistory();
  const status = String(job?.status || "completed");
  if (refreshAttempted && !refreshSucceeded) {
    toast("Research finished, but the catalog could not refresh yet. Reopen this job to retry.", "warning", 6000);
  } else if (refreshAttempted && status === "completed") {
    toast("Research completed and the catalog was refreshed.");
  } else if (refreshAttempted && status === "partial") {
    toast("Research completed with warnings and the catalog was refreshed.", "warning", 6000);
  } else if (refreshAttempted && ["failed", "interrupted"].includes(status)) {
    toast(`Research ${status}. The terminal details are available in the research window.`, "error", 6000);
  }
}

async function pollResearchJob(id, generation) {
  clearTimeout(state.research.timer);
  if (generation !== state.research.generation) return;
  try {
    const job = await apiFetch(`${API.researchJobs}/${encodeURIComponent(id)}`);
    if (generation !== state.research.generation) return;
    state.research.failures = 0;
    renderResearchJob(job);
    if (TERMINAL_RESEARCH_STATES.has(String(job.status || "").toLowerCase())) {
      await finishResearchJob(job);
      return;
    }
    state.research.timer = setTimeout(() => pollResearchJob(id, generation), document.hidden ? 4500 : 2200);
  } catch (error) {
    if (generation !== state.research.generation || error.status === 401) return;
    state.research.failures += 1;
    $("research-progress-detail").textContent = "The connection dropped. The job may still be running; reconnecting now.";
    if (state.research.failures <= 4) {
      const delay = Math.min(2000 * (2 ** (state.research.failures - 1)), 15000);
      state.research.timer = setTimeout(() => pollResearchJob(id, generation), delay);
    } else {
      state.research.busy = false;
      $("research-submit").disabled = false;
      $("research-warnings").innerHTML = `<div class="research-warning">${icon("warning")}<span>Live progress could not reconnect. Open this job from Recent research to check its final state.</span></div>`;
    }
  }
}

async function startResearch() {
  if (state.research.busy) return;
  const mode = document.querySelector('input[name="research-mode"]:checked')?.value || "sample";
  if (mode === "live" && !researchIsLive()) {
    $("research-form-message").textContent = "Live research is unavailable. Choose saved public research explicitly.";
    return;
  }
  $("research-form-message").textContent = "";
  state.research.busy = true;
  state.research.failures = 0;
  state.research.generation += 1;
  const generation = state.research.generation;
  clearTimeout(state.research.timer);
  const placeholder = {
    id: "",
    status: "queued",
    stage: mode === "sample" ? "Opening saved public research" : "Submitting live research",
    mode,
    cards: [],
    review_cards: [],
    warnings: [],
    events: [],
    metrics: {},
  };
  renderResearchJob(placeholder);
  try {
    const job = await apiFetch(API.researchJobs, {
      method: "POST",
      body: JSON.stringify({
        count: Number($("research-count").value),
        sector: $("research-sector").value,
        mode,
        request_id: requestId(),
      }),
    });
    renderResearchJob(job);
    if (!job?.id) throw new ApiError("The server started research without returning a job ID.");
    if (TERMINAL_RESEARCH_STATES.has(String(job.status || "").toLowerCase())) await finishResearchJob(job);
    else await pollResearchJob(job.id, generation);
  } catch (error) {
    if (error.status === 409 && error.payload?.id) {
      await pollResearchJob(error.payload.id, generation);
      return;
    }
    state.research.busy = false;
    $("research-submit").disabled = false;
    if (error.status !== 401) {
      $("research-form-message").textContent = error.message;
      $("research-warnings").innerHTML = `<div class="research-warning">${icon("warning")}<span>${escapeHTML(error.message)} No saved result was substituted.</span></div>`;
    }
  }
}

function renderResearchHistory() {
  const section = $("research-history");
  const jobs = asArray(state.research.history);
  section.hidden = !jobs.length;
  $("research-history-list").innerHTML = jobs.slice(0, 8).map((job) => {
    const count = finiteNumber(job?.qualified_count, asArray(job?.cards).length);
    const mode = job?.mode === "sample" ? "Saved public research" : "Live research";
    return `<button class="history-job" type="button" data-history-id="${escapeHTML(job?.id || "")}"><span><strong>${escapeHTML(mode)} · ${plural(count, "profile")}</strong><span>${escapeHTML(formatDate(job?.created_at || job?.updated_at))} · ${escapeHTML(job?.sector || "All sectors")}</span></span><b>${escapeHTML(sentenceCase(job?.status || "unknown"))}</b></button>`;
  }).join("");
}

async function loadResearchHistory() {
  try {
    const payload = await apiFetch(API.researchJobs);
    state.research.history = asArray(payload?.jobs);
    renderResearchHistory();
  } catch (error) {
    if (error.status !== 401) $("research-history").hidden = true;
  }
}

async function openHistoryJob(id) {
  if (!id) return;
  state.research.generation += 1;
  const generation = state.research.generation;
  clearTimeout(state.research.timer);
  state.research.busy = true;
  try {
    const job = await apiFetch(`${API.researchJobs}/${encodeURIComponent(id)}`);
    state.research.busy = !TERMINAL_RESEARCH_STATES.has(String(job.status || "").toLowerCase());
    renderResearchJob(job);
    if (state.research.busy) pollResearchJob(id, generation);
    else await finishResearchJob(job);
  } catch (error) {
    state.research.busy = false;
    if (error.status !== 401) toast(`Could not open that research job: ${error.message}`, "error");
  }
}

async function openResearch(trigger = document.activeElement) {
  openLayer($("research-layer"), trigger);
  renderResearchStatus();
  if (!state.research.status && !state.research.statusError) await loadResearchStatus();
  await loadResearchHistory();
}

function integrationStatusClass(status) {
  const normalized = normalizedText(status).replace(/\s+/g, "-");
  return ["ready", "connected", "ok", "configured", "available", "active"].includes(normalized) ? "" : normalized;
}

function renderIntegrations() {
  const container = $("integration-list");
  const refreshButton = $("refresh-founder-data");
  if (state.integrationsError) {
    container.innerHTML = `<div class="research-warning">${icon("warning")}<span>${escapeHTML(state.integrationsError)}</span></div>`;
    refreshButton.hidden = true;
    return;
  }
  if (!state.integrations) return;
  const modules = asArray(state.integrations.modules);
  container.innerHTML = modules.length ? modules.map((module) => {
    const status = String(module?.status || "unknown");
    return `<div class="integration-row"><div><strong>${escapeHTML(module?.name || module?.id || "Data module")}</strong><small>${escapeHTML(module?.message || "No connection note was provided.")}</small></div><span class="integration-state ${escapeHTML(integrationStatusClass(status))}">${escapeHTML(sentenceCase(status))}</span></div>`;
  }).join("") : `<div class="integration-row"><div><strong>No modules reported</strong><small>The server did not return module status details.</small></div><span class="integration-state unconfigured">Unknown</span></div>`;
  refreshButton.hidden = !state.integrations.founders_configured;
  $("founder-sync-note").textContent = state.integrations.founders_last_synced ? `Founder data last refreshed ${formatDate(state.integrations.founders_last_synced)}.` : (state.integrations.founders_configured ? "Founder data is configured but has no reported refresh time." : "Founder refresh is unavailable until its source is configured.");
}

async function loadIntegrations() {
  state.integrationsError = "";
  try {
    state.integrations = await apiFetch(API.integrations);
  } catch (error) {
    if (error.status !== 401) state.integrationsError = error.message;
  } finally {
    renderIntegrations();
  }
}

async function syncFounders() {
  const button = $("refresh-founder-data");
  if (!state.integrations?.founders_configured || button.disabled) return;
  const oldHTML = button.innerHTML;
  button.disabled = true;
  button.textContent = "Refreshing…";
  $("founder-sync-note").textContent = "Refreshing the configured read-only founder source…";
  try {
    const result = await apiFetch(API.foundersSync, { method: "POST", body: "{}", timeout: 55000 });
    $("founder-sync-note").textContent = result.message || `${plural(finiteNumber(result.companies), "company")} refreshed at ${formatDate(result.synced_at)}.`;
    toast(result.message || "Founder data refreshed.");
    await Promise.allSettled([loadIntegrations(), loadCatalog({ quiet: true })]);
  } catch (error) {
    if (error.status !== 401) {
      $("founder-sync-note").textContent = error.message;
      toast(`Founder data could not refresh: ${error.message}`, "error");
    }
  } finally {
    button.disabled = false;
    button.innerHTML = oldHTML;
  }
}

function openMethodology(trigger = document.activeElement) {
  openLayer($("methodology-layer"), trigger);
  renderAuthState();
  loadIntegrations();
}

function openLayer(layer, trigger = document.activeElement) {
  if (activeLayer && activeLayer !== layer) closeLayer({ restoreFocus: false });
  activeLayer = layer;
  layerReturnFocus = trigger instanceof HTMLElement ? trigger : null;
  layer.hidden = false;
  document.body.classList.add("has-layer");
  requestAnimationFrame(() => {
    const target = layer.querySelector("[role='dialog']") || layer.querySelector(".drawer") || layer;
    target.focus({ preventScroll: true });
  });
}

function closeLayer({ restoreFocus = true } = {}) {
  if (!activeLayer) return;
  const closing = activeLayer;
  activeLayer = null;
  closing.hidden = true;
  if (closing === $("company-layer")) {
    state.detailGeneration += 1;
    state.detailCompany = null;
    state.detailFallback = false;
  }
  document.body.classList.remove("has-layer");
  if (restoreFocus && layerReturnFocus?.isConnected) layerReturnFocus.focus({ preventScroll: true });
  layerReturnFocus = null;
}

function trapLayerFocus(event) {
  if (!activeLayer || event.key !== "Tab") return;
  const focusable = [...activeLayer.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])')].filter((element) => !element.hidden && element.getClientRects().length);
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function openSidebar() {
  $("sidebar-scrim").hidden = false;
  document.body.classList.add("sidebar-open");
  $("sidebar").querySelector("button")?.focus();
}

function closeSidebar() {
  $("sidebar-scrim").hidden = true;
  document.body.classList.remove("sidebar-open");
}

function bindEvents() {
  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-close-layer]");
    if (close) {
      closeLayer();
      return;
    }

    const viewButton = event.target.closest("[data-view]");
    if (viewButton) {
      setView(viewButton.dataset.view);
      return;
    }

    const openCompanyButton = event.target.closest("[data-open-company]");
    if (openCompanyButton) {
      openCompany(openCompanyButton.dataset.openCompany, openCompanyButton);
      return;
    }

    const saveButton = event.target.closest("[data-toggle-save]");
    if (saveButton) {
      toggleShortlist(saveButton.dataset.toggleSave);
      return;
    }

    const compareButton = event.target.closest("[data-toggle-compare]");
    if (compareButton) {
      toggleCompare(compareButton.dataset.toggleCompare);
      return;
    }

    const removeCompare = event.target.closest("[data-remove-compare]");
    if (removeCompare) {
      toggleCompare(removeCompare.dataset.removeCompare);
      return;
    }

    const pageButton = event.target.closest("[data-page]");
    if (pageButton) {
      state.page = Number(pageButton.dataset.page);
      renderDirectory();
      $("directory-title").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    const exportButton = event.target.closest("[data-export]");
    if (exportButton) {
      exportEvidence(exportButton.dataset.export);
      return;
    }

    const historyButton = event.target.closest("[data-history-id]");
    if (historyButton) {
      openHistoryJob(historyButton.dataset.historyId);
      return;
    }

    const noteButton = event.target.closest("[data-save-note]");
    if (noteButton) {
      saveCompanyNote(noteButton.dataset.saveNote);
      return;
    }

    const addFilterButton = event.target.closest("[data-add-filter]");
    if (addFilterButton) {
      addFilter(addFilterButton.dataset.addFilter);
      return;
    }

    const removeFilterButton = event.target.closest("[data-remove-filter]");
    if (removeFilterButton) {
      removeFilter(removeFilterButton.dataset.removeFilter);
      return;
    }

    const signalChip = event.target.closest("[data-signal-chip]");
    if (signalChip) {
      const key = signalChip.dataset.signalChip;
      const signals = state.filters.signals;
      state.filters.signals = signals.includes(key) ? signals.filter((item) => item !== key) : [...signals, key];
      state.page = 1;
      populateSectorFilters();
      renderDirectory();
      return;
    }

    const clusterLink = event.target.closest("[data-view-cluster]");
    if (clusterLink) {
      hideTip();
      viewCluster(clusterLink.dataset.viewCluster);
      return;
    }

    const sectorRow = event.target.closest("[data-sector-row]");
    if (sectorRow) {
      const key = sectorRow.dataset.sectorRow;
      state.selectedSector = state.selectedSector === key ? "" : key;
      renderSectorTable();
      return;
    }

    const trendButton = event.target.closest("[data-trend-metric]");
    if (trendButton) {
      state.trendMetric = trendButton.dataset.trendMetric;
      renderTrendChart();
      return;
    }

    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) {
      if (!event.target.closest("#export-menu")) $("export-menu").open = false;
      if (!event.target.closest("#add-filter")) $("add-filter").open = false;
      return;
    }
    const actions = {
      "show-directory": () => setView("directory", { scroll: false }),
      "browse-directory": () => { closeLayer({ restoreFocus: false }); setView("directory"); },
      "open-sidebar": openSidebar,
      "close-sidebar": closeSidebar,
      "clear-filters": clearFilters,
      "retry-catalog": () => loadCatalog(),
      "open-research": () => openResearch(event.target.closest("button") || document.activeElement),
      "open-methodology": () => openMethodology(event.target.closest("button") || document.activeElement),
      "open-compare": () => openComparison(event.target.closest("button") || document.activeElement),
      "clear-compare": () => { state.compareIds = []; renderCompareState(); },
      "refresh-research-history": loadResearchHistory,
      "sync-founders": syncFounders,
    };
    actions[action]?.();
  });

  const updateSearch = debounce((value) => {
    state.filters.query = value.trim();
    state.page = 1;
    renderDirectory();
  }, 100);
  $("catalog-search").addEventListener("input", (event) => updateSearch(event.target.value));

  $("startup-filter").addEventListener("change", (event) => { state.filters.hideNonStartups = event.target.checked; state.page = 1; renderDirectory(); });
  $("nj-filter").addEventListener("change", (event) => { state.filters.nj = event.target.value; state.page = 1; renderDirectory(); });
  $("sector-filter").addEventListener("change", (event) => { state.filters.sector = event.target.value; state.page = 1; renderDirectory(); });
  $("record-filter").addEventListener("change", (event) => { state.filters.recordType = event.target.value; state.page = 1; renderDirectory(); });
  $("sort-filter").addEventListener("change", (event) => { state.filters.sort = event.target.value; state.page = 1; renderDirectory(); });
  $("cluster-filter").addEventListener("change", (event) => { state.filters.cluster = event.target.value; state.page = 1; renderDirectory(); });
  $("score-filter").addEventListener("change", (event) => { state.filters.minScore = Number(event.target.value) || 0; state.page = 1; renderDirectory(); });
  $("young-filter").addEventListener("change", (event) => { state.filters.youngOnly = event.target.checked; state.page = 1; renderDirectory(); });
  $("region-cluster").addEventListener("change", (event) => { state.regionCluster = event.target.value; renderRegionMap(); });

  const tipTarget = (event) => event.target instanceof Element ? event.target.closest("[data-tip]") : null;
  document.addEventListener("mouseover", (event) => { const target = tipTarget(event); if (target) showTip(target); });
  document.addEventListener("mouseout", (event) => { if (tipTarget(event) && !tipTarget({ target: event.relatedTarget })) hideTip(); });
  document.addEventListener("focusin", (event) => { const target = tipTarget(event); if (target) showTip(target); else hideTip(); });
  document.addEventListener("scroll", hideTip, { passive: true });
  $("per-page").addEventListener("change", (event) => { state.filters.perPage = Number(event.target.value); state.page = 1; renderDirectory(); });

  $("unlock-form").addEventListener("submit", (event) => {
    event.preventDefault();
    unlockWorkspace($("access-token").value, $("unlock-message"), event.submitter);
  });
  $("settings-unlock-form").addEventListener("submit", (event) => {
    event.preventDefault();
    unlockWorkspace($("settings-access-token").value, $("session-access-copy"), event.submitter);
  });
  $("research-form").addEventListener("submit", (event) => {
    event.preventDefault();
    startResearch();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (activeLayer) closeLayer();
      else if (document.body.classList.contains("sidebar-open")) closeSidebar();
      else if (document.activeElement === $("catalog-search") && $("catalog-search").value) {
        $("catalog-search").value = "";
        state.filters.query = "";
        renderDirectory();
      }
      return;
    }
    trapLayerFocus(event);
    const target = event.target;
    if ((event.key === "Enter" || event.key === " ") && target instanceof Element && target.matches("g[data-view-cluster]")) {
      event.preventDefault();
      hideTip();
      viewCluster(target.dataset.viewCluster);
      return;
    }
    const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
    if (!activeLayer && ((event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) || (event.key === "/" && !typing))) {
      event.preventDefault();
      $("catalog-search").focus();
    }
  });

  document.addEventListener("visibilitychange", () => {
    const job = state.research.job;
    if (!document.hidden && state.research.busy && job?.id) {
      clearTimeout(state.research.timer);
      pollResearchJob(job.id, state.research.generation);
    }
  });
}

async function initialize() {
  bindEvents();
  renderFilterSlots();
  renderDirectory();
  renderAuthState();
  renderResearchStatus();
  await loadHealth();
  if (state.auth.required && !state.auth.token) return;
  const initialView = location.hash.slice(1);
  if (["sectors", "scoring", "shortlist"].includes(initialView)) setView(initialView, { scroll: false });
  await Promise.allSettled([loadCatalog(), loadShortlist(), loadResearchStatus()]);
}

initialize();
