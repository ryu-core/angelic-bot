import { useEffect, useMemo, useState } from "react";

function mediaQuery(query) {
  return typeof window !== "undefined" ? window.matchMedia(query) : null;
}

function readCapabilities() {
  const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  const isMobile = Boolean(mediaQuery("(max-width: 680px)")?.matches);
  const compactNavigation = Boolean(mediaQuery("(max-width: 1000px)")?.matches);
  const reducedMotion = Boolean(mediaQuery("(prefers-reduced-motion: reduce)")?.matches);
  const saveData = Boolean(connection?.saveData);

  return {
    isMobile,
    mobile: isMobile,
    compactNavigation,
    reducedMotion,
    prefersReducedMotion: reducedMotion,
    saveData,
  };
}

export function useCapabilities() {
  const [capabilities, setCapabilities] = useState(readCapabilities);

  useEffect(() => {
    const mobile = mediaQuery("(max-width: 680px)");
    const compactNavigation = mediaQuery("(max-width: 1000px)");
    const motion = mediaQuery("(prefers-reduced-motion: reduce)");
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    const update = () => setCapabilities(readCapabilities());

    mobile?.addEventListener?.("change", update);
    compactNavigation?.addEventListener?.("change", update);
    motion?.addEventListener?.("change", update);
    connection?.addEventListener?.("change", update);

    return () => {
      mobile?.removeEventListener?.("change", update);
      compactNavigation?.removeEventListener?.("change", update);
      motion?.removeEventListener?.("change", update);
      connection?.removeEventListener?.("change", update);
    };
  }, []);

  return useMemo(() => capabilities, [capabilities]);
}
