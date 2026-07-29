const $ = (id) => document.getElementById(id);

let browsing = false;

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

function renderSongs(songs) {
  const list = $("list");
  if (!browsing) {
    list.hidden = true;
    list.innerHTML = "";
    return;
  }
  list.hidden = false;
  if (!songs.length) {
    list.innerHTML = `<p class="meta">No songs in the library yet. Enter a seed and click Discover.</p>`;
    return;
  }
  list.innerHTML = songs
    .map(
      (s) => `
    <article class="card">
      <h3>${escapeHtml(s.song_name)}</h3>
      <div class="meta">
        ${escapeHtml(s.movie_name || "—")} · ${s.release_year || "year?"} · ${escapeHtml(s.composer_name || "")}
      </div>
      <div class="meta">
        Singers: ${(s.singers || []).map(escapeHtml).join(", ") || "—"}
        ${s.lyricists?.length ? ` · Lyricist: ${s.lyricists.map(escapeHtml).join(", ")}` : ""}
      </div>
      <div class="tags">
        <span class="tag">pop ${Math.round(s.popularity)}</span>
        <span class="tag">${escapeHtml(s.playability)}</span>
        <span class="tag">${escapeHtml(s.discovered_via || "manual")}</span>
        ${(s.moods || []).map((m) => `<span class="tag">${escapeHtml(m)}</span>`).join("")}
      </div>
    </article>`,
    )
    .join("");
}

async function refreshStats() {
  const stats = await api("/api/stats");
  renderBrowseCount(stats.total_songs);
  return stats;
}

async function loadBrowse() {
  $("status").textContent = "Loading library…";
  const params = new URLSearchParams({ limit: "100" });
  const seed = $("seed").value.trim();
  if (seed) params.set("composer", seed);
  const [stats, songs] = await Promise.all([
    api("/api/stats"),
    api(`/api/songs?${params}`),
  ]);
  renderBrowseCount(stats.total_songs);
  renderSongs(songs);
  $("status").textContent = browsing ? `${songs.length} shown` : "";
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
    $("status").textContent = "";
  }
});

refreshStats().catch((e) => ($("status").textContent = e.message));
