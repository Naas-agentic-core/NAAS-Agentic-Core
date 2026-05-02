"use client";

import { useEffect, useState } from "react";
import CogniForgeApp from "./components/CogniForgeApp";

export default function ClientOnlyApp() {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return <CogniForgeApp />;
}
