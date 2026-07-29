const $ = (id) => document.getElementById(id);

const DISCOVERY_YEAR_MIN = 1950;
const DISCOVERY_YEAR_MAX = 2100;

let browsing = false;
/** @type {Array<Record<string, any>>} */
let allSongs = [];
/** @type {{ from: number | null, to: number | null }} */
let yearRange = { from: null, to: null };

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
    loadBrowse().catch((e) => ($("status").textContent = e.message));
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

async function loadBrowse() {
  $("status").textContent = "Loading library…";
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
    const batch = await api(`/api/songs?${params}`);
    songs.push(...batch);
    if (batch.length < pageSize) break;
    offset += pageSize;
    if (offset > 20000) break;
  }
  renderSongs(songs);
}

async function pollDiscoverJob(jobId) {
  for (let i = 0; i < 3600; i++) {
    const job = await api(`/api/discover/jobs/${jobId}`);
    const filmProgress = job.cursor_json?.film_index
      ? ` · film ${job.cursor_json.film_index}/${job.cursor_json.films_total || "?"}`
      : "";
    $("status").textContent =
      `${job.seed}: ${job.phase} — ${job.message || job.status}` +
      ` · inserted ${job.inserted}, updated ${job.updated}` +
      filmProgress;
    await refreshStats().catch(() => {});
    await refreshJobs().catch(() => {});
    if (browsing) {
      await loadBrowse().catch(() => {});
    }
    if (job.status === "completed" || job.status === "failed" || job.status === "archived") {
      return job;
    }
    await new Promise((r) => setTimeout(r, 2500));
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

function openJobDetails(job) {
  const cursor = job.cursor_json || {};
  const listPages = cursor.wiki_list_pages || [];
  const filmographyPages = cursor.filmography_pages || [];
  const filmPages = cursor.film_pages || [];
  $("job-details-status").textContent = `${job.status} · ${job.phase}`;
  $("job-details-title").textContent = job.entity_label || job.seed;
  $("job-details-meta").textContent =
    `Seed “${job.seed}” · inserted ${job.inserted}, updated ${job.updated}, skipped ${job.skipped}` +
    (job.message ? ` · ${job.message}` : "");
  $("job-details-body").innerHTML = `
    <h3>Song list / discography pages</h3>
    ${pageListHtml(listPages, "No Wikipedia list pages recorded yet for this seed.")}
    <h3>Filmography source pages</h3>
    ${pageListHtml(filmographyPages, "No filmography pages recorded yet.")}
    <h3>Film pages scanned for soundtracks</h3>
    ${pageListHtml(filmPages, "No film soundtrack pages recorded yet.")}
    ${job.error ? `<h3>Error</h3><p class="meta">${escapeHtml(job.error)}</p>` : ""}
  `;
  $("job-details").showModal();
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
        job.cursor_json?.films_total
          ? ` · film ${job.cursor_json.film_index || 0}/${job.cursor_json.films_total}`
          : "";
      const pages = (job.cursor_json?.wiki_list_pages || []).length;
      const active = job.status === "pending" || job.status === "running";
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

let jobsPollTimer = null;
function startJobsPolling() {
  if (jobsPollTimer) return;
  jobsPollTimer = setInterval(() => {
    refreshJobs().catch(() => {});
  }, 4000);
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
    await loadBrowse().catch((e) => ($("status").textContent = e.message));
  } else {
    $("list").hidden = true;
    $("list").innerHTML = "";
    allSongs = [];
    $("status").textContent = "";
  }
});

bindYearRange();
refreshStats().catch((e) => ($("status").textContent = e.message));
refreshJobs()
  .then((jobs) => {
    if (jobs?.some((j) => j.status === "pending" || j.status === "running")) {
      startJobsPolling();
    }
  })
  .catch((e) => ($("status").textContent = e.message));

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
