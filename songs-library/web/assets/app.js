const $ = (id) => document.getElementById(id);

let browsing = false;
/** @type {Array<Record<string, any>>} */
let allSongs = [];

const COLUMNS = [
  { key: "song_name", label: "Song", get: (s) => s.song_name || "" },
  { key: "movie_name", label: "Movie", get: (s) => s.movie_name || "" },
  {
    key: "release_year",
    label: "Year",
    get: (s) => (s.release_year == null ? "" : String(s.release_year)),
  },
  { key: "composer_name", label: "Composer", get: (s) => s.composer_name || "" },
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

function getColumnFilters() {
  const filters = {};
  for (const col of COLUMNS) {
    const input = document.querySelector(`[data-filter="${col.key}"]`);
    filters[col.key] = (input?.value || "").trim().toLowerCase();
  }
  return filters;
}

function filterSongs(songs) {
  const filters = getColumnFilters();
  return songs.filter((song) =>
    COLUMNS.every((col) => {
      const needle = filters[col.key];
      if (!needle) return true;
      return col.get(song).toLowerCase().includes(needle);
    }),
  );
}

function ensureTableShell() {
  const list = $("list");
  if (list.querySelector(".songs-table")) return;

  const headFilters = COLUMNS.map(
    (col) => `
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
      </th>`,
  ).join("");

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
      // Don't trigger Discover while filtering the table.
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

  const activeFilters = Object.values(getColumnFilters()).filter(Boolean).length;
  $("status").textContent = browsing
    ? `${filtered.length} shown` +
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
  const params = new URLSearchParams({ limit: "200" });
  const [stats, songs] = await Promise.all([
    api("/api/stats"),
    api(`/api/songs?${params}`),
  ]);
  renderBrowseCount(stats.total_songs);
  renderSongs(songs);
}

async function discover() {
  const seed = $("seed").value.trim();
  if (!seed) {
    $("status").textContent = "Enter a seed first (composer, film, or artist).";
    $("seed").focus();
    return;
  }
  $("discover").disabled = true;
  $("status").textContent = `Discovering songs for “${seed}” via Wikipedia / Wikidata…`;
  try {
    const result = await api("/api/discover", {
      method: "POST",
      body: JSON.stringify({
        seeds: [seed],
        limit_per_seed: 200,
      }),
    });
    const row = result.results?.[0];
    const err = row?.error ? ` — ${row.error}` : "";
    $("status").textContent =
      `Found ${row?.found ?? 0}, inserted ${result.total_inserted}, skipped ${result.total_skipped}` +
      (row?.entity_label ? ` (${row.entity_label})` : "") +
      err;
    browsing = true;
    $("browse").classList.add("active");
    await loadBrowse();
  } catch (err) {
    $("status").textContent = err.message || String(err);
  } finally {
    $("discover").disabled = false;
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
    await loadBrowse().catch((e) => ($("status").textContent = e.message));
  } else {
    $("list").hidden = true;
    $("list").innerHTML = "";
    allSongs = [];
    $("status").textContent = "";
  }
});

refreshStats().catch((e) => ($("status").textContent = e.message));
