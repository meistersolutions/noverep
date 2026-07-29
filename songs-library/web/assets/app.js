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
      `${job.phase}: ${job.message || job.status}` +
      ` · inserted ${job.inserted}, updated ${job.updated}` +
      filmProgress;
    await refreshStats().catch(() => {});
    if (browsing) {
      await loadBrowse().catch(() => {});
    }
    if (job.status === "completed" || job.status === "failed") {
      return job;
    }
    await new Promise((r) => setTimeout(r, 2500));
  }
  throw new Error("Discover job timed out waiting for completion");
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

    if (result.job_ids?.length) {
      const job = await pollDiscoverJob(result.job_ids[0]);
      const err = job.error ? ` — ${job.error}` : "";
      $("status").textContent =
        `Discovery ${job.status}: inserted ${job.inserted}, updated ${job.updated}, skipped ${job.skipped}` +
        (job.entity_label ? ` (${job.entity_label})` : "") +
        err;
      await loadBrowse();
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
