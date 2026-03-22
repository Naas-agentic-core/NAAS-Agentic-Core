"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { errorTracker } from "./utils/errorTracker";

const LEGACY_SCRIPTS = [
  {
    id: "legacy-react",
    src: "https://cdn.jsdelivr.net/npm/react@17/umd/react.production.min.js"
  },
  {
    id: "legacy-react-dom",
    src: "https://cdn.jsdelivr.net/npm/react-dom@17/umd/react-dom.production.min.js"
  },
  {
    id: "legacy-babel",
    src: "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"
  },
  {
    id: "legacy-showdown",
    src: "https://cdn.jsdelivr.net/npm/showdown/dist/showdown.min.js"
  },
  {
    id: "legacy-axios",
    src: "https://cdn.jsdelivr.net/npm/axios/dist/axios.min.js"
  },
  {
    id: "legacy-performance",
    src: "/performance-monitor.js"
  }
];

const LEGACY_APP_SCRIPT = {
  id: "legacy-app",
  src: "/js/legacy-app.jsx",
  type: "text/babel",
  attributes: { "data-presets": "env,react" }
};

const LEGACY_MOUNT_TIMEOUT_MS = 45000;

const ensureScript = (script) =>
  new Promise((resolve, reject) => {
    if (typeof window === "undefined") {
      resolve();
      return;
    }

    if (document.getElementById(script.id)) {
      resolve();
      return;
    }

    const existing = document.querySelector(`script[src="${script.src}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error(`Failed to load ${script.src}`)),
        { once: true }
      );
      return;
    }

    const element = document.createElement("script");
    element.id = script.id;
    element.src = script.src;
    element.async = false;

    if (script.type) {
      element.type = script.type;
    }

    if (script.attributes) {
      Object.entries(script.attributes).forEach(([key, value]) => {
        element.setAttribute(key, value);
      });
    }

    element.addEventListener("load", resolve, { once: true });
    element.addEventListener(
      "error",
      () => reject(new Error(`Failed to load ${script.src}`)),
      { once: true }
    );

    document.head.appendChild(element);
  });

const waitForLegacyMount = () =>
  new Promise((resolve, reject) => {
    if (typeof window === "undefined") {
      resolve();
      return;
    }

    if (window.__legacyAppMounted) {
      resolve();
      return;
    }

    const root = document.getElementById("root");
    if (root && root.childElementCount > 0) {
      window.__legacyAppMounted = true;
      resolve();
      return;
    }

    let timeoutId;

    const cleanup = () => {
      window.removeEventListener("legacy-app-mounted", handleMounted);
      window.removeEventListener("legacy-app-error", handleError);
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };

    const handleMounted = () => {
      cleanup();
      window.__legacyAppMounted = true;
      resolve();
    };

    const handleError = (event) => {
      cleanup();
      const message = event?.detail?.message || "تعذر تشغيل الواجهة.";
      reject(new Error(message));
    };

    window.addEventListener("legacy-app-mounted", handleMounted, { once: true });
    window.addEventListener("legacy-app-error", handleError, { once: true });

    timeoutId = setTimeout(() => {
      cleanup();
      reject(
        new Error("انتهت مهلة تحميل الواجهة. تحقق من الاتصال ثم أعد المحاولة.")
      );
    }, LEGACY_MOUNT_TIMEOUT_MS);
  });

export default function LegacyLoader() {
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const dependenciesReadyRef = useRef(false);
  const pendingMountedRef = useRef(false);

  const loadingMessage = useMemo(() => {
    if (status === "error") {
      return "تعذر تحميل الواجهة. يرجى إعادة المحاولة.";
    }
    return "جارٍ تشغيل واجهة CogniForge...";
  }, [status]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const handleMounted = () => {
      if (dependenciesReadyRef.current) {
        setError(null);
        setStatus("ready");
      } else {
        pendingMountedRef.current = true;
      }
    };

    window.addEventListener("legacy-app-mounted", handleMounted);

    return () => {
      window.removeEventListener("legacy-app-mounted", handleMounted);
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (window.__legacyAppLoaded && window.__legacyAppMounted) {
      setStatus("ready");
      return;
    }

    window.__legacyAppLoading = true;

    const load = async () => {
      try {
        for (const script of LEGACY_SCRIPTS) {
          await ensureScript(script);
        }
        if (!window.__legacyAppLoaded) {
          await ensureScript(LEGACY_APP_SCRIPT);
          window.__legacyAppLoaded = true;
        }
        dependenciesReadyRef.current = true;
        if (pendingMountedRef.current || window.__legacyAppMounted) {
          setError(null);
          setStatus("ready");
          return;
        }
        await waitForLegacyMount();
        setStatus("ready");
      } catch (loadError) {
        errorTracker.reportError(loadError);
        setError(loadError);
        setStatus("error");
      } finally {
        window.__legacyAppLoading = false;
      }
    };

    load();
  }, []);

  if (status === "ready") {
    return null;
  }

  return (
    <div aria-live="polite" className="legacy-loader">
      <p>{loadingMessage}</p>
      {error ? (
        <>
          <p className="legacy-loader__error">
            {String(error.message || error)}
          </p>
          <button type="button" onClick={() => window.location.reload()}>
            إعادة تحميل الواجهة
          </button>
        </>
      ) : null}
    </div>
  );
}
