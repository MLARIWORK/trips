(async function () {
  const res = await fetch("manifest.json", { cache: "no-cache" });
  const data = await res.json();

  document.title = data.site.title || "Trips";
  document.getElementById("site-title").textContent = data.site.title || "Trips";
  const subtitle = document.getElementById("site-subtitle");
  if (data.site.subtitle) subtitle.textContent = data.site.subtitle;
  else subtitle.remove();

  const footer = document.getElementById("site-footer");
  const total = data.trips.reduce((n, t) => n + t.photo_count, 0);
  footer.textContent = data.trips.length
    ? `${data.trips.length} trip${data.trips.length === 1 ? "" : "s"} · ${total} photos`
    : "";
  if (data.site.repo) {
    const a = document.createElement("a");
    a.href = data.site.repo;
    a.textContent = "GitHub";
    footer.append(" · ", a);
  }

  const grid = document.getElementById("trip-grid");
  if (!data.trips.length) {
    document.getElementById("empty-state").hidden = false;
    return;
  }

  for (const trip of data.trips) {
    const card = document.createElement("a");
    card.className = "trip-card";
    card.href = "trip.html?t=" + encodeURIComponent(trip.slug);

    const img = document.createElement("img");
    img.src = encodeURI(trip.cover.thumb);
    img.alt = trip.title;
    img.loading = "lazy";
    img.decoding = "async";

    const body = document.createElement("div");
    body.className = "card-body";
    const h2 = document.createElement("h2");
    h2.textContent = trip.title;
    const meta = document.createElement("p");
    meta.className = "card-meta";
    meta.textContent = [trip.location, trip.dates,
      `${trip.photo_count} photo${trip.photo_count === 1 ? "" : "s"}`]
      .filter(Boolean).join(" · ");

    body.append(h2, meta);
    card.append(img, body);
    grid.append(card);
  }
})();
