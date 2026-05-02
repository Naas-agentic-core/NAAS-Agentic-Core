"use client";

import dynamic from "next/dynamic";

const CogniForgeApp = dynamic(() => import("./components/CogniForgeApp"), {
  ssr: false,
});

export default function Home() {
  return (
    <main>
      <CogniForgeApp />
    </main>
  );
}
