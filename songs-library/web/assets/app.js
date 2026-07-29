const $ = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
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

function renderStats(stats) {
  const composers = Object.entries(stats.by_composer || {})
    .slice(0, 5)
    .map(([k, v]) => `${k}: ${v}`)
    .join(" · ");
  $("stats").innerHTML = `<strong>${stats.total_songs}</strong>songs in library<div>${composers || "Empty — run discover when ready"}</div>`;
}

function renderSongs(songs) {
  if (!songs.length) {
    $("list").innerHTML = `<p class="meta">No songs yet. Add manually via API or click Discover later.</p>`;
    return;
  }
  $("list").innerHTML = songs
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
        ${(s.moods || []).map((m) => `<span class="tag">${escapeHtml(m)}</span>`).join("")}
      </div>
    </article>`,
    )
    .join("");
}

async function load() {
  $("status").textContent = "Loading…";
  const params = new URLSearchParams();
  if ($("q").value.trim()) params.set("q", $("q").value.trim());
  if ($("composer").value) params.set("composer", $("composer").value);
  params.set("limit", "80");
  const [stats, songs] = await Promise.all([
    api("/api/stats"),
    api(`/api/songs?${params}`),
  ]);
  renderStats(stats);
  renderSongs(songs);
  $("status").textContent = `${songs.length} shown`;
}

async function discover() {
  $("discover").disabled = true;
  $("status").textContent = "Discovering from Wikidata (may take a minute)…";
  try {
    const result = await api("/api/discover", {
      method: "POST",
      body: JSON.stringify({
        seeds: ["Ilaiyaraaja", "A. R. Rahman", "Yuvan Shankar Raja"],
        limit_per_seed: 300,
      }),
    });
    $("status").textContent = `Inserted ${result.total_inserted}, skipped ${result.total_skipped}`;
    await load();
  } catch (err) {
    $("status").textContent = err.message || String(err);
  } finally {
    $("discover").disabled = false;
  }
}

$("refresh").addEventListener("click", () => load().catch((e) => ($("status").textContent = e.message)));
$("discover").addEventListener("click", discover);
$("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") load().catch((e) => ($("status").textContent = e.message));
});
load().catch((e) => ($("status").textContent = e.message));
