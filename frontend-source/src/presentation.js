// Presentation helpers only. Resource values are never estimated or simulated.
export function boundedNumber(value, fallback, min, max) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.min(max, Math.max(min, n)) : fallback;
}

export function measuredGiB(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 ? `${(n / 1024 ** 3).toFixed(1)} GiB` : null;
}

export function settingsMatches(row, query) {
  return [row[0], row[1], row[3]].join(' ').toLowerCase().includes(query.trim().toLowerCase());
}

export function recentStudioImages(images) {
  const seen = new Set();
  return images.filter(image => {
    const path = image.path || image.image_path;
    if (!path || image.deleted || image.hidden || image.deletedAt || image.deleted_at) return false;
    const key = path.replace(/\\/g, '/').toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 12);
}
