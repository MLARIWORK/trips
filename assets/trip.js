(async function () {
  const slug = new URLSearchParams(location.search).get("t");
  const res = await fetch("manifest.json", { cache: "no-cache" });
  const data = await res.json();
  const trip = data.trips.find((t) => t.slug === slug);

  if (!trip) {
    document.getElementById("trip-title").textContent = "Trip not found";
    return;
  }

  document.title = `${trip.title} — ${data.site.title || "Trips"}`;
  document.getElementById("trip-title").textContent = trip.title;
  document.getElementById("trip-meta").textContent =
    [trip.location, trip.dates,
      `${trip.photo_count} photo${trip.photo_count === 1 ? "" : "s"}`]
      .filter(Boolean).join(" · ");

  const notes = document.getElementById("trip-notes");
  if (trip.notes_md) {
    if (window.marked) {
      notes.innerHTML = marked.parse(trip.notes_md);
    } else {
      trip.notes_md.split(/\n{2,}/).forEach((para) => {
        const p = document.createElement("p");
        p.textContent = para;
        notes.append(p);
      });
    }
  }

  // ---- photo grid ----
  const grid = document.getElementById("photo-grid");
  trip.photos.forEach((photo, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.addEventListener("click", () => openLightbox(i));
    const img = document.createElement("img");
    img.src = encodeURI(photo.thumb);
    img.alt = photo.caption || photo.name;
    if (photo.caption) img.title = photo.caption;
    img.loading = "lazy";
    img.decoding = "async";
    btn.append(img);
    grid.append(btn);
  });

  // ---- lightbox ----
  const lb = document.getElementById("lightbox");
  const lbImg = document.getElementById("lb-img");
  const lbCaption = document.getElementById("lb-caption");
  const lbCounter = document.getElementById("lb-counter");
  const lbTaken = document.getElementById("lb-taken");
  const lbDownload = document.getElementById("lb-download");
  let current = 0;

  function humanSize(n) {
    if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
    return n + " B";
  }

  function show(i) {
    current = (i + trip.photos.length) % trip.photos.length;
    const photo = trip.photos[current];
    lbImg.src = encodeURI(photo.web);
    lbImg.alt = photo.caption || photo.name;
    lbCaption.textContent = photo.caption;
    lbCaption.style.display = photo.caption ? "" : "none";
    lbCounter.textContent = `${current + 1} / ${trip.photos.length}`;
    lbTaken.textContent = photo.taken;
    lbDownload.href = encodeURI(photo.original);
    lbDownload.setAttribute("download", photo.name);
    lbDownload.textContent = `Download original (${humanSize(photo.bytes)})`;
    // Preload neighbours for snappy arrows.
    for (const j of [current + 1, current - 1]) {
      const n = (j + trip.photos.length) % trip.photos.length;
      new Image().src = encodeURI(trip.photos[n].web);
    }
  }

  function openLightbox(i) {
    show(i);
    lb.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    lb.hidden = true;
    lbImg.src = "";
    document.body.style.overflow = "";
  }

  document.getElementById("lb-close").addEventListener("click", closeLightbox);
  document.getElementById("lb-prev").addEventListener("click", () => show(current - 1));
  document.getElementById("lb-next").addEventListener("click", () => show(current + 1));
  lb.addEventListener("click", (e) => {
    if (e.target === lb || e.target.classList.contains("lb-figure")) closeLightbox();
  });
  document.addEventListener("keydown", (e) => {
    if (lb.hidden) return;
    if (e.key === "Escape") closeLightbox();
    else if (e.key === "ArrowLeft") show(current - 1);
    else if (e.key === "ArrowRight") show(current + 1);
  });
})();
