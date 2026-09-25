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

const TERMINAL_RESEARCH_STATES = new Set(["completed", "partial", "failed", "interrupted"]);
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
    sort: "research",
    perPage: 24,
  },
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
  $("directory-section").hidden = locked;
  $("stat-grid").hidden = locked;
  $("catalog-notices").hidden = locked || !state.notices.length;

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
  state.catalogLoading = false;
  state.catalogError = "";
  state.auth.serverOk = true;
  populateSectorFilters();
  renderCatalogChrome();
  renderDirectory();
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
  $("snapshot-date").textContent = state.snapshotDate ? formatDate(state.snapshotDate, { month: "long", day: "numeric", year: "numeric" }) : "Date not reported";
  $("sidebar-snapshot").textContent = state.snapshotDate ? `Catalog snapshot · ${formatDate(state.snapshotDate)}` : "Catalog snapshot date not reported";

  const statItems = [
    [companyTotal, "Catalog records", "Research, filings and leads"],
    [finiteNumber(stats.nj_supported), "NJ supported", "Location evidence attached"],
    [finiteNumber(stats.sources), "Linked sources", "Unique public URLs"],
    [finiteNumber(stats.team_reviewed), "Team reviewed", "Leadership research"],
  ];
  $("stat-grid").innerHTML = statItems.map(([value, label, detail]) => `<div class="stat-card"><span>${escapeHTML(label)}</span><strong>${formatNumber(value)}</strong><small>${escapeHTML(detail)}</small></div>`).join("");

  const noticeArea = $("catalog-notices");
  noticeArea.innerHTML = state.notices.length ? `<details class="catalog-notice-disclosure"><summary>${icon("info")}<span><strong>${plural(state.notices.length, "catalog note")}</strong><small>Source scope, evidence limits and interpretation</small></span>${icon("chevron")}</summary><div class="catalog-notice-list">${state.notices.map((notice) => `<div class="catalog-notice">${icon("info")}<span>${escapeHTML(notice)}</span></div>`).join("")}</div></details>` : "";
  noticeArea.hidden = !state.notices.length || (state.auth.required && !state.auth.token);
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
    name: (a, b) => String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
    coverage: (a, b) => coverageCount(b) - coverageCount(a) || finiteNumber(b.source_count) - finiteNumber(a.source_count) || String(a.name || "").localeCompare(String(b.name || "")),
    sources: (a, b) => finiteNumber(b.source_count) - finiteNumber(a.source_count) || coverageCount(b) - coverageCount(a) || String(a.name || "").localeCompare(String(b.name || "")),
    updated: (a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")) || String(a.name || "").localeCompare(String(b.name || "")),
  };
  if (state.filters.sort === "research") return companies;
  companies = [...companies].sort(sorters[state.filters.sort] || sorters.name);
  return companies;
}

function filtersAreActive() {
  return Boolean(state.filters.query || !state.filters.hideNonStartups || state.filters.nj !== "all" || state.filters.sector !== "all" || state.filters.recordType !== "all" || state.filters.sort !== "research");
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

function clearFilters() {
  state.filters = { ...state.filters, query: "", hideNonStartups: true, nj: "all", sector: "all", recordType: "all", sort: "research" };
  state.page = 1;
  $("catalog-search").value = "";
  $("startup-filter").checked = true;
  $("nj-filter").value = "all";
  $("sector-filter").value = "all";
  $("record-filter").value = "all";
  $("sort-filter").value = "research";
  renderDirectory();
}

function setView(view, { scroll = true } = {}) {
  state.view = view === "shortlist" ? "shortlist" : "directory";
  state.page = 1;
  document.querySelectorAll("[data-view]").forEach((button) => {
    const active = button.dataset.view === state.view;
    button.classList.toggle("is-active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (state.view === "shortlist") {
    $("breadcrumb-current").textContent = "Shortlist";
    $("view-eyebrow").innerHTML = "<span></span> Your saved company records";
    $("page-title").innerHTML = "Your saved companies,<br><em>ready for a closer look.</em>";
    $("page-description").textContent = "Keep notes beside the evidence, compare up to three records and return to the source whenever a claim needs a closer look.";
    $("directory-title").textContent = "Shortlisted companies";
  } else {
    $("breadcrumb-current").textContent = "Company directory";
    $("view-eyebrow").innerHTML = "<span></span> New Jersey company records";
    $("page-title").innerHTML = "Company intelligence,<br><em>with the receipts.</em>";
    $("page-description").textContent = "Discover companies, inspect the public evidence and keep the unknowns in view. Coverage shows what we can document. It is not a prediction of success.";
    $("directory-title").textContent = "Company directory";
  }
  closeSidebar();
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
    <div class="profile-stat-row"><div class="profile-stat"><strong>${coverageCount(company)}/4</strong><span>Evidence pillars</span></div><div class="profile-stat"><strong>${formatNumber(company.source_count)}</strong><span>Unique sources</span></div><div class="profile-stat"><strong>${escapeHTML(formatDate(company.updated_at, { month: "short", day: "numeric", year: "numeric" }))}</strong><span>Record updated</span></div></div>
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
  const pillarRows = PILLARS.map(({ key, label }) => {
    const cells = companies.map((company) => {
      const pillar = pillarFor(company, key);
      const summary = pillar.summary || (pillar.status === "missing" ? "No supported evidence attached." : "Summary not reported.");
      const metrics = pillar.metrics.slice(0, 3).map((metric) => `<span>${escapeHTML(metric?.label || "Metric")}: ${escapeHTML(metric?.value ?? "Unknown")}</span>`).join("");
      return `<div class="compare-cell"><span class="status-badge ${pillar.status}">${escapeHTML(sentenceCase(pillar.status))}</span><p>${escapeHTML(summary)}</p>${metrics ? `<div class="compare-mini-metrics">${metrics}</div>` : ""}</div>`;
    }).join("");
    return `<div class="compare-row"><div class="compare-label">${escapeHTML(label)}</div>${cells}</div>`;
  }).join("");
  container.innerHTML = `<div class="compare-table" style="--compare-columns:${companies.length}"><div class="compare-row"><div class="compare-label">Company</div>${headers}</div><div class="compare-row"><div class="compare-label">Record</div>${overview}</div>${pillarRows}</div>`;
}

function openComparison(trigger = document.activeElement) {
  renderComparison();
  openLayer($("compare-layer"), trigger);
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
        note: "Evidence coverage is not a prediction of success or an investment score.",
      },
      companies: companies.map((company) => ({
        ...company,
        shortlist: ids.has(String(company.id)),
        note: state.shortlist.notes[String(company.id)] || "",
      })),
    };
    downloadBlob(JSON.stringify(payload, null, 2), "application/json;charset=utf-8", `garden-state-evidence-${today}.json`);
  } else {
    const headers = ["company_id", "company_name", "sector", "location", "nj_status", "record_type", "pillar", "source_title", "source_url", "quote", "published_at", "observed_at", "source_type"];
    const rows = [headers];
    companies.forEach((company) => {
      const evidence = asArray(company.evidence);
      if (!evidence.length) {
        rows.push([company.id, company.name, company.sector, company.location, company.nj_status, company.record_type, "", "", "", "", "", "", ""]);
        return;
      }
      evidence.forEach((source) => rows.push([company.id, company.name, company.sector, company.location, company.nj_status, company.record_type, source?.pillar, source?.title, source?.url, source?.quote, source?.published_at, source?.observed_at, source?.source_type]));
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

    const action = event.target.closest("[data-action]")?.dataset.action;
    if (!action) {
      if (!event.target.closest("#export-menu")) $("export-menu").open = false;
      return;
    }
    const actions = {
      "show-directory": () => setView("directory", { scroll: false }),
      "browse-directory": () => { closeLayer({ restoreFocus: false }); setView("directory"); },
      "open-sidebar": openSidebar,
      "close-sidebar": closeSidebar,
      "toggle-filters": () => {
        const panel = $("filter-panel");
        const open = panel.classList.toggle("is-open");
        document.querySelector("[data-action='toggle-filters']")?.setAttribute("aria-expanded", String(open));
      },
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
  renderDirectory();
  renderAuthState();
  renderResearchStatus();
  await loadHealth();
  if (state.auth.required && !state.auth.token) return;
  await Promise.allSettled([loadCatalog(), loadShortlist(), loadResearchStatus()]);
}

initialize();
