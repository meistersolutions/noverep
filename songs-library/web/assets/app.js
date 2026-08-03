const $ = (id) => document.getElementById(id);

const DISCOVERY_YEAR_MIN = 1950;
const DISCOVERY_YEAR_MAX = 2100;

let browsing = false;
/** @type {Array<Record<string, any>>} */
let allSongs = [];
/** @type {{ from: number | null, to: number | null }} */
let yearRange = { from: null, to: null };
/** Composer filter from /?composer=… (also used when reloading browse). */
let browseComposer = "";

const COLUMNS = [
  { key: "song_name", label: "Song", get: (s) => s.song_name || "" },
  { key: "movie_name", label: "Movie", get: (s) => s.movie_name || "" },
  {
    key: "release_year",
    label: "Year",
    get: (s) => (s.release_year == null ? "" : String(s.release_year)),
    // Year uses the player-style from/to range instead of a free-text column filter.
    skipTextFilter: true,
  },
  { key: "composer_name", label: "Composer", get: (s) => s.composer_name || "" },
  { key: "language", label: "Language", get: (s) => s.language || "" },
  {
    key: "directors",
    label: "Director",
    get: (s) => (s.directors || []).join(", "),
  },
  {
    key: "actors",
    label: "Actors",
    get: (s) => (s.actors || []).join(", "),
  },
  {
    key: "actresses",
    label: "Actresses",
    get: (s) => (s.actresses || []).join(", "),
  },
  {
    key: "singers",
    label: "Singers",
    get: (s) => (s.singers || []).join(", "),
  },
  {
    key: "lyricists",
    label: "Lyricists",
    get: (s) => (s.lyricists || []).join(", "),
  },
  {
    key: "popularity",
    label: "Popularity",
    get: (s) => (s.popularity == null ? "" : String(Math.round(s.popularity))),
  },
  {
    key: "youtube_view_count",
    label: "YT views",
    get: (s) => {
      if (s.youtube_view_count == null) return "";
      const n = Number(s.youtube_view_count);
      if (!Number.isFinite(n)) return "";
      if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
      if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
      if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
      return String(n);
    },
  },
  { key: "playability", label: "Playability", get: (s) => s.playability || "" },
  {
    key: "discovered_via",
    label: "Source",
    get: (s) => s.discovered_via || "manual",
  },
];

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : res.statusText,
    );
  }
  return res.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderBrowseCount(total) {
  $("browse-count").textContent = String(total ?? 0);
}

function validateYearField(raw) {
  const trimmed = String(raw || "").trim();
  if (!trimmed) return { value: null, error: null };
  if (!/^\d{4}$/.test(trimmed)) {
    return { value: null, error: "Enter a 4-digit year (e.g. 2015)" };
  }
  const year = Number(trimmed);
  if (year < DISCOVERY_YEAR_MIN || year > DISCOVERY_YEAR_MAX) {
    return {
      value: null,
      error: `Year must be ${DISCOVERY_YEAR_MIN}–${DISCOVERY_YEAR_MAX}`,
    };
  }
  return { value: year, error: null };
}

function validateYearRange(from, to) {
  if (from !== null && to !== null && from > to) {
    return '"From" year must be on or before "To" year';
  }
  return null;
}

function setYearError(message) {
  const el = $("year-error");
  if (!message) {
    el.hidden = true;
    el.textContent = "";
    $("year-from").classList.remove("invalid");
    $("year-to").classList.remove("invalid");
    return;
  }
  el.hidden = false;
  el.textContent = message;
}

function commitYearRange({ reload = true } = {}) {
  const fromResult = validateYearField($("year-from").value);
  const toResult = validateYearField($("year-to").value);

  $("year-from").classList.toggle("invalid", !!fromResult.error);
  $("year-to").classList.toggle("invalid", !!toResult.error);

  if (fromResult.error || toResult.error) {
    setYearError(fromResult.error || toResult.error);
    return false;
  }

  const rangeErr = validateYearRange(fromResult.value, toResult.value);
  if (rangeErr) {
    setYearError(rangeErr);
    $("year-from").classList.add("invalid");
    $("year-to").classList.add("invalid");
    return false;
  }

  setYearError(null);
  const unchanged =
    yearRange.from === fromResult.value && yearRange.to === toResult.value;
  yearRange = { from: fromResult.value, to: toResult.value };

  if (browsing && !unchanged && reload) {
    loadBrowse({ composer: browseComposer }).catch((e) => ($("status").textContent = e.message));
  } else if (browsing) {
    renderFilteredRows();
  }
  return true;
}

function getColumnFilters() {
  const filters = {};
  for (const col of COLUMNS) {
    if (col.skipTextFilter) continue;
    const input = document.querySelector(`[data-filter="${col.key}"]`);
    filters[col.key] = (input?.value || "").trim().toLowerCase();
  }
  return filters;
}

function matchesYearRange(song) {
  const y = song.release_year;
  // Match player recommendation behavior: keep unknown years.
  if (y == null) return true;
  if (yearRange.from != null && y < yearRange.from) return false;
  if (yearRange.to != null && y > yearRange.to) return false;
  return true;
}

function filterSongs(songs) {
  const filters = getColumnFilters();
  return songs.filter((song) => {
    if (!matchesYearRange(song)) return false;
    return COLUMNS.every((col) => {
      if (col.skipTextFilter) return true;
      const needle = filters[col.key];
      if (!needle) return true;
      return col.get(song).toLowerCase().includes(needle);
    });
  });
}

function ensureTableShell() {
  const list = $("list");
  if (list.querySelector(".songs-table")) return;

  const headFilters = COLUMNS.map((col) => {
    if (col.key === "release_year") {
      return `
        <th scope="col">
          <div class="th-label">${escapeHtml(col.label)}</div>
          <div class="year-col-hint">Uses From / To above</div>
        </th>`;
    }
    return `
      <th scope="col">
        <div class="th-label">${escapeHtml(col.label)}</div>
        <input
          type="search"
          class="col-filter"
          data-filter="${escapeHtml(col.key)}"
          placeholder="Filter…"
          aria-label="Filter ${escapeHtml(col.label)}"
          autocomplete="off"
        />
      </th>`;
  }).join("");

  list.innerHTML = `
    <div class="table-wrap">
      <table class="songs-table">
        <thead>
          <tr class="filter-row">${headFilters}</tr>
        </thead>
        <tbody id="songs-body"></tbody>
      </table>
    </div>
  `;

  list.querySelectorAll(".col-filter").forEach((input) => {
    input.addEventListener("input", () => {
      renderFilteredRows();
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") e.preventDefault();
    });
  });
}

function renderFilteredRows() {
  const body = $("songs-body");
  if (!body) return;

  const filtered = filterSongs(allSongs);
  if (!filtered.length) {
    body.innerHTML = `
      <tr>
        <td class="empty" colspan="${COLUMNS.length}">
          No songs match the current filters.
        </td>
      </tr>`;
  } else {
    body.innerHTML = filtered
      .map(
        (s) => `
      <tr>
        ${COLUMNS.map((col) => {
          const value = col.get(s);
          const display = value || "—";
          const cls = value ? "" : ' class="muted"';
          return `<td${cls}>${escapeHtml(display)}</td>`;
        }).join("")}
      </tr>`,
      )
      .join("");
  }

  const textFilters = Object.values(getColumnFilters()).filter(Boolean).length;
  const yearActive = yearRange.from != null || yearRange.to != null;
  const activeFilters = textFilters + (yearActive ? 1 : 0);
  const yearLabel = yearActive
    ? ` · years ${yearRange.from ?? "…"}–${yearRange.to ?? "…"}`
    : "";

  $("status").textContent = browsing
    ? `${filtered.length} shown` +
      yearLabel +
      (activeFilters ? ` · ${activeFilters} filter${activeFilters === 1 ? "" : "s"} active` : "") +
      (allSongs.length !== filtered.length ? ` of ${allSongs.length}` : "")
    : "";
}

function renderSongs(songs) {
  const list = $("list");
  if (!browsing) {
    list.hidden = true;
    list.innerHTML = "";
    allSongs = [];
    return;
  }
  list.hidden = false;
  allSongs = songs;

  if (!songs.length) {
    list.innerHTML = `<p class="meta">No songs in the library yet. Enter a seed and click Discover.</p>`;
    $("status").textContent = "0 shown";
    return;
  }

  ensureTableShell();
  renderFilteredRows();
}

async function refreshStats() {
  const stats = await api("/api/stats");
  renderBrowseCount(stats.total_songs);
  return stats;
}

async function loadBrowse(options = {}) {
  if (Object.prototype.hasOwnProperty.call(options, "composer")) {
    browseComposer = (options.composer || "").trim();
  }
  const composer = browseComposer;
  $("status").textContent = composer
    ? `Loading songs for “${composer}”…`
    : "Loading library…";
  const stats = await api("/api/stats");
  renderBrowseCount(stats.total_songs);

  const songs = [];
  const pageSize = 200;
  let offset = 0;
  while (true) {
    const params = new URLSearchParams({
      limit: String(pageSize),
      offset: String(offset),
    });
    if (yearRange.from != null) params.set("year_from", String(yearRange.from));
    if (yearRange.to != null) params.set("year_to", String(yearRange.to));
    if (composer) params.set("composer", composer);
    const batch = await api(`/api/songs?${params}`);
    songs.push(...batch);
    if (batch.length < pageSize) break;
    offset += pageSize;
    if (offset > 20000) break;
  }
  renderSongs(songs);
  if (composer) {
    const input = document.querySelector('.col-filter[data-filter="composer_name"]');
    if (input) {
      input.value = composer;
      renderFilteredRows();
    }
  }
}

async function pollDiscoverJob(jobId) {
  for (let i = 0; i < 3600; i++) {
    const job = await api(`/api/discover/jobs/${jobId}`);
    const filmProgress = job.films_total
      ? ` · film ${job.film_index || 0}/${job.films_total}`
      : "";
    $("status").textContent =
      `${job.seed}: ${job.phase} — ${job.message || job.status}` +
      ` · inserted ${job.inserted}, updated ${job.updated}` +
      filmProgress;
    await refreshStats().catch(() => {});
    await refreshJobs().catch(() => {});
    // Do NOT reload the full catalog every tick — major Neon egress source.
    if (job.status === "completed" || job.status === "failed" || job.status === "archived") {
      if (browsing) await loadBrowse().catch(() => {});
      return job;
    }
    await new Promise((r) => setTimeout(r, 5000));
  }
  throw new Error("Discover job timed out waiting for completion");
}

function wikiUrl(title) {
  return `https://en.wikipedia.org/wiki/${encodeURIComponent(String(title).replace(/ /g, "_"))}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function pageListHtml(pages, emptyLabel) {
  if (!pages?.length) {
    return `<p class="meta">${escapeHtml(emptyLabel)}</p>`;
  }
  return `<ul class="wiki-pages">${pages
    .map(
      (title) =>
        `<li><a href="${wikiUrl(title)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}</a></li>`,
    )
    .join("")}</ul>`;
}

async function openJobDetails(job) {
  $("job-details-status").textContent = `${job.status} · ${job.phase}`;
  $("job-details-title").textContent = job.entity_label || job.seed;
  $("job-details-meta").textContent =
    `Seed “${job.seed}” · inserted ${job.inserted}, updated ${job.updated}, skipped ${job.skipped}` +
    (job.message ? ` · ${job.message}` : "");
  $("job-details-body").innerHTML = `<p class="meta">Loading Wikipedia pages…</p>`;
  $("job-details").showModal();
  try {
    const pages = await api(`/api/discover/jobs/${encodeURIComponent(job.id)}/pages`);
    $("job-details-body").innerHTML = `
      <h3>Song list / discography pages</h3>
      ${pageListHtml(pages.wiki_list_pages || [], "No Wikipedia list pages recorded yet for this seed.")}
      <h3>Filmography source pages</h3>
      ${pageListHtml(pages.filmography_pages || [], "No filmography pages recorded yet.")}
      <h3>Film pages scanned for soundtracks</h3>
      ${pageListHtml(pages.film_pages || [], "No film soundtrack pages recorded yet.")}
      ${job.error ? `<h3>Error</h3><p class="meta">${escapeHtml(job.error)}</p>` : ""}
    `;
  } catch (err) {
    $("job-details-body").innerHTML =
      `<p class="meta">${escapeHtml(err.message || String(err))}</p>` +
      (job.error ? `<h3>Error</h3><p class="meta">${escapeHtml(job.error)}</p>` : "");
  }
}

function renderJobs(jobs) {
  const host = $("jobs-list");
  if (!jobs?.length) {
    host.innerHTML = `<p class="meta">No discovery jobs yet. Enter a seed and click Discover.</p>`;
    return;
  }
  host.innerHTML = jobs
    .map((job) => {
      const label = job.entity_label || job.seed;
      const filmProgress =
        job.films_total
          ? ` · film ${job.film_index || 0}/${job.films_total}`
          : "";
      const pages = job.wiki_list_page_count || 0;
      const active = job.status === "pending" || job.status === "running";
      const canResume = job.status !== "archived";
      const filmIndex = job.film_index || 0;
      const resumeLabel =
        job.status === "running" || job.status === "pending"
          ? filmIndex > 0
            ? "Resume"
            : "Restart"
          : filmIndex > 0
            ? "Resume"
            : "Restart";
      const endLabel = active ? "End & archive" : "Archive";
      return `
        <article class="job-row ${escapeHtml(job.status)}" data-job-id="${escapeHtml(job.id)}">
          <div>
            <p class="job-seed">${escapeHtml(label)}</p>
            <p class="job-meta">
              <span class="job-badge ${escapeHtml(job.status)}">${escapeHtml(job.status)}</span>
              ${escapeHtml(job.phase)}${filmProgress}
              · inserted ${job.inserted}
              ${pages ? ` · ${pages} wiki list page(s)` : ""}
              ${job.message ? `<br>${escapeHtml(job.message)}` : ""}
            </p>
          </div>
          <div class="job-actions">
            <button type="button" class="ghost job-details-btn" data-job-id="${escapeHtml(job.id)}">Details</button>
            ${
              canResume
                ? `<button
              type="button"
              class="ghost job-resume-btn"
              data-job-id="${escapeHtml(job.id)}"
              data-reset="${filmIndex > 0 ? "0" : "1"}"
              title="${
                filmIndex > 0
                  ? "Re-queue and continue the film crawl from where it left off"
                  : "Re-queue this seed so the background worker runs it again"
              }"
            >${resumeLabel}</button>`
                : ""
            }
            <button
              type="button"
              class="ghost danger job-end-btn"
              data-job-id="${escapeHtml(job.id)}"
              data-active="${active ? "1" : "0"}"
              title="${active ? "Stop this seed and remove it from the list" : "Hide this job from the list"}"
            >${endLabel}</button>
          </div>
        </article>
      `;
    })
    .join("");

  host.querySelectorAll(".job-details-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-job-id");
      try {
        const job = await api(`/api/discover/jobs/${id}`);
        openJobDetails(job);
      } catch (err) {
        $("status").textContent = err.message || String(err);
      }
    });
  });

  host.querySelectorAll(".job-resume-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-job-id");
      const reset = btn.getAttribute("data-reset") === "1";
      const confirmMsg = reset
        ? "Restart this seed from the beginning? Existing songs stay in the library (duplicates are skipped)."
        : "Resume this seed from the last film checkpoint?";
      if (!window.confirm(confirmMsg)) return;
      btn.disabled = true;
      try {
        await api(`/api/discover/jobs/${id}/restart?reset=${reset ? "true" : "false"}`, {
          method: "POST",
        });
        $("status").textContent = reset
          ? "Seed requeued from the beginning."
          : "Seed resume queued.";
        startJobsPolling();
        await refreshJobs();
      } catch (err) {
        $("status").textContent = err.message || String(err);
        btn.disabled = false;
      }
    });
  });

  host.querySelectorAll(".job-end-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-job-id");
      const active = btn.getAttribute("data-active") === "1";
      const confirmMsg = active
        ? "End this seed discovery and archive it? Progress so far is kept; the job will stop."
        : "Archive this job and hide it from the list?";
      if (!window.confirm(confirmMsg)) return;
      btn.disabled = true;
      try {
        await api(`/api/discover/jobs/${id}/end`, { method: "POST" });
        $("status").textContent = active
          ? "Seed ended and archived."
          : "Job archived.";
        await refreshJobs();
        if (browsing) await loadBrowse().catch(() => {});
      } catch (err) {
        $("status").textContent = err.message || String(err);
        btn.disabled = false;
      }
    });
  });
}

async function refreshJobs() {
  const jobs = await api("/api/discover/jobs?limit=20");
  renderJobs(jobs);
  return jobs;
}

function renderWorkersStatus(w) {
  const host = $("workers-status");
  if (!host) return;
  const batch = w.last_resolve_batch;
  const batchLine = batch?.at
    ? `Last batch (${batch.source || "?"}): attempted ${batch.attempted}, resolved ${batch.resolved}, failed ${batch.failed} · ${new Date(batch.at).toLocaleString()}`
    : "No resolve batch recorded yet since last deploy (worker may still be starting).";
  const apiLabel = w.youtube_api_configured ? "yes" : "no";
  host.innerHTML = `
    <div class="workers-metrics">
      <div class="workers-metric"><span>Mapped</span><strong>${Number(w.mapped).toLocaleString()}</strong></div>
      <div class="workers-metric"><span>Unmapped</span><strong>${Number(w.metadata_only).toLocaleString()}</strong></div>
      <div class="workers-metric"><span>Mapped %</span><strong>${w.mapped_pct}%</strong></div>
      <div class="workers-metric"><span>API key</span><strong>${apiLabel}</strong></div>
      <div class="workers-metric"><span>Blocks</span><strong>${w.consecutive_blocks}</strong></div>
    </div>
    <p class="workers-batch">${batchLine}</p>
    ${w.hint ? `<p class="workers-hint">${escapeHtml(w.hint)}</p>` : ""}
  `;
}

async function refreshWorkers() {
  const w = await api("/api/workers/status");
  renderWorkersStatus(w);
  return w;
}

let workersPollTimer = null;
function startWorkersPolling() {
  if (workersPollTimer) return;
  workersPollTimer = setInterval(() => {
    refreshWorkers().catch(() => {});
  }, 60000);
}

async function runResolveBatch() {
  const btn = $("resolve-run");
  btn.disabled = true;
  $("status").textContent = "Running YouTube resolve batch (20)…";
  try {
    const result = await api("/api/resolve/youtube", {
      method: "POST",
      body: JSON.stringify({ limit: 20 }),
    });
    $("status").textContent =
      `Resolve batch: attempted ${result.attempted}, resolved ${result.resolved}, failed ${result.failed}`;
    await refreshWorkers();
    await refreshStats();
  } catch (err) {
    $("status").textContent = err.message || String(err);
  } finally {
    btn.disabled = false;
  }
}

let jobsPollTimer = null;
function startJobsPolling() {
  if (jobsPollTimer) return;
  jobsPollTimer = setInterval(() => {
    refreshJobs().catch(() => {});
  }, 15000);
}

async function discover() {
  const seed = $("seed").value.trim();
  if (!seed) {
    $("status").textContent = "Enter a seed first (composer, film, or artist).";
    $("seed").focus();
    return;
  }
  if (!commitYearRange({ reload: false })) {
    $("status").textContent = "Fix the year range before discovering.";
    return;
  }
  $("discover").disabled = true;
  $("status").textContent = `Queuing continuous discovery for “${seed}”…`;
  try {
    const result = await api("/api/discover", {
      method: "POST",
      body: JSON.stringify({
        seeds: [seed],
        limit_per_seed: 0,
        force: true,
      }),
    });
    browsing = true;
    $("browse").classList.add("active");
    startJobsPolling();
    await refreshJobs();

    if (result.job_ids?.length) {
      $("status").textContent =
        `Discovery queued for “${seed}”. Watching progress in Background discovery…`;
      // Follow this job in the status line, but keep the jobs list as the main view.
      pollDiscoverJob(result.job_ids[0])
        .then(async (job) => {
          const err = job.error ? ` — ${job.error}` : "";
          $("status").textContent =
            `Discovery ${job.status}: inserted ${job.inserted}, updated ${job.updated}, skipped ${job.skipped}` +
            (job.entity_label ? ` (${job.entity_label})` : "") +
            err;
          await refreshJobs();
          if (browsing) await loadBrowse();
        })
        .catch((err) => {
          $("status").textContent = err.message || String(err);
        });
    } else {
      const row = result.results?.[0];
      const err = row?.error ? ` — ${row.error}` : "";
      $("status").textContent =
        `Found ${row?.found ?? 0}, inserted ${result.total_inserted}, updated ${result.total_updated || 0}, skipped ${result.total_skipped}` +
        (row?.entity_label ? ` (${row.entity_label})` : "") +
        err;
      await loadBrowse();
    }
  } catch (err) {
    $("status").textContent = err.message || String(err);
  } finally {
    $("discover").disabled = false;
  }
}

function bindYearRange() {
  const apply = () => commitYearRange({ reload: true });
  $("year-from").addEventListener("blur", apply);
  $("year-to").addEventListener("blur", apply);
  for (const id of ["year-from", "year-to"]) {
    $(id).addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        apply();
      }
    });
    $(id).addEventListener("input", () => {
      setYearError(null);
      $(id).classList.remove("invalid");
    });
  }
}

$("discover").addEventListener("click", discover);
$("seed").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    discover();
  }
});
$("browse").addEventListener("click", async () => {
  browsing = !browsing;
  $("browse").classList.toggle("active", browsing);
  if (browsing) {
    if (!commitYearRange({ reload: false })) return;
    await loadBrowse({ composer: browseComposer }).catch((e) => ($("status").textContent = e.message));
  } else {
    browseComposer = "";
    $("list").hidden = true;
    $("list").innerHTML = "";
    allSongs = [];
    $("status").textContent = "";
  }
});

bindYearRange();
refreshStats().catch((e) => ($("status").textContent = e.message));
refreshWorkers()
  .then(() => startWorkersPolling())
  .catch((e) => {
    if ($("workers-status")) {
      $("workers-status").innerHTML = `<p class="meta">Could not load worker status: ${escapeHtml(e.message || String(e))}</p>`;
    }
  });
$("resolve-refresh")?.addEventListener("click", () => {
  refreshWorkers().catch((e) => ($("status").textContent = e.message));
});
$("resolve-run")?.addEventListener("click", runResolveBatch);
refreshJobs()
  .then((jobs) => {
    if (jobs?.some((j) => j.status === "pending" || j.status === "running")) {
      startJobsPolling();
    }
  })
  .catch((e) => ($("status").textContent = e.message));

(async () => {
  const composer = new URLSearchParams(window.location.search).get("composer");
  if (!composer?.trim()) return;
  browsing = true;
  $("browse").classList.add("active");
  if (!commitYearRange({ reload: false })) return;
  try {
    await loadBrowse({ composer: composer.trim() });
  } catch (e) {
    $("status").textContent = e.message || String(e);
  }
})();

function toggleAddPanel(show) {
  const panel = $("add-panel");
  panel.hidden = !show;
  if (show) $("add-song").focus();
}

async function submitManualAdd() {
  const songName = $("add-song").value.trim();
  if (!songName) {
    $("status").textContent = "Song name is required.";
    $("add-song").focus();
    return;
  }
  const yearRaw = $("add-year").value.trim();
  let releaseYear = null;
  if (yearRaw) {
    const yearResult = validateYearField(yearRaw);
    if (yearResult.error) {
      $("status").textContent = yearResult.error;
      return;
    }
    releaseYear = yearResult.value;
  }
  $("add-submit").disabled = true;
  try {
    await api("/api/songs", {
      method: "POST",
      body: JSON.stringify({
        song_name: songName,
        movie_name: $("add-movie").value.trim() || null,
        composer_name: $("add-composer").value.trim() || null,
        release_year: releaseYear,
        discovered_via: "manual",
      }),
    });
    $("add-song").value = "";
    $("add-movie").value = "";
    $("add-composer").value = "";
    $("add-year").value = "";
    toggleAddPanel(false);
    $("status").textContent = `Added “${songName}”.`;
    await refreshStats();
    if (browsing) await loadBrowse();
  } catch (err) {
    $("status").textContent = err.message || String(err);
  } finally {
    $("add-submit").disabled = false;
  }
}

$("toggle-add").addEventListener("click", () => {
  const panel = $("add-panel");
  toggleAddPanel(panel.hidden);
});
$("add-cancel").addEventListener("click", () => toggleAddPanel(false));
$("add-submit").addEventListener("click", submitManualAdd);
