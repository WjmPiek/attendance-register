import { useEffect, useState } from "react";
import { apiRequest } from "../api/client";

export function isRequisitionsWeb() {
  return (
    !window.matchMedia("(max-width: 760px)").matches &&
    !/Android|iPhone|iPad|iPod/i.test(navigator.userAgent) &&
    !window.Capacitor?.isNativePlatform?.()
  );
}

export function useRequisitionsAccess(userId) {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => {
    let active = true;
    const load = () => {
      if (!isRequisitionsWeb()) {
        setAllowed(false);
        return;
      }
      apiRequest("/requisitions/access")
        .then((result) => {
          if (active)
            setAllowed(Boolean(result.enabled) && isRequisitionsWeb());
        })
        .catch(() => {
          if (active) setAllowed(false);
        });
    };
    const media = window.matchMedia("(max-width: 760px)");
    load();
    media.addEventListener("change", load);
    return () => {
      active = false;
      media.removeEventListener("change", load);
    };
  }, [userId]);
  return allowed;
}

export const rand = (cents) =>
  `R ${(Number(cents || 0) / 100).toLocaleString("en-ZA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
export const saToday = () =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "Africa/Johannesburg",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());

export function lineTotal(lines) {
  return lines.reduce(
    (sum, l) => sum + Math.round(Number(l.amount || 0) * 100),
    0
  );
}
