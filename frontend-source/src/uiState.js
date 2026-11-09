import { useEffect, useState } from "react";
import { resolveTheme, THEMES, virtualRows } from "./uiLogic.js";
export function readUI(key, fallback) {
  try {
    const value = JSON.parse(localStorage.getItem("offlinegpt-ui-" + key));
    if (value == null) return fallback;
    if (
      fallback !== null &&
      (typeof value !== typeof fallback ||
        Array.isArray(value) !== Array.isArray(fallback))
    )
      return fallback;
    return value;
  } catch {
    return fallback;
  }
}
export function writeUI(key, value) {
  try {
    localStorage.setItem("offlinegpt-ui-" + key, JSON.stringify(value));
  } catch {}
}
export function useUIState(key, fallback) {
  const [v, set] = useState(() => readUI(key, fallback));
  useEffect(() => writeUI(key, v), [key, v]);
  return [v, set];
}
export function applyLocalDisplay() {
  const r = document.documentElement,
    mode = readUI("themeMode", null);
  if (THEMES.includes(mode))
    r.dataset.theme = resolveTheme(
      mode,
      matchMedia("(prefers-color-scheme: light)").matches,
    );
  r.dataset.contrast = String(mode === "contrast");
  r.style.zoom = String(
    Math.max(0.8, Math.min(1.5, Number(readUI("zoom", 1)) || 1)),
  );
  r.dataset.developer = String(readUI("developer", false) === true);
}
export function useVirtualGrid(count, ref, options = {}) {
  const [bounds, set] = useState({ width: 800, height: 600, scrollTop: 0 });
  useEffect(() => {
    const e = ref.current;
    if (!e) return;
    let frame = 0;
    const measure = () => {
      frame = 0;
      set({
        width: Math.max(1, e.clientWidth - 48),
        height: e.clientHeight,
        scrollTop: e.scrollTop,
      });
    };
    const update = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    const resize = new ResizeObserver(update);
    resize.observe(e);
    e.addEventListener("scroll", update, { passive: true });
    measure();
    return () => {
      resize.disconnect();
      e.removeEventListener("scroll", update);
      cancelAnimationFrame(frame);
    };
  }, [ref]);
  return virtualRows({ count, ...bounds, ...options });
}
