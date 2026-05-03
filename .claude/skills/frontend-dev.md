# Frontend Development — Next.js 16 + Arabic RTL + WebSocket

> CogniForge frontend skill. Next.js 16.1.5, React 18, Arabic RTL, KaTeX math, WebSocket.

---

## Project Structure

```
frontend/
├── app/
│   ├── layout.jsx          # Root layout — RTL Arabic, imports global CSS
│   ├── page.jsx            # Entry point → ClientOnlyApp
│   ├── ClientOnlyApp.jsx   # Hydration guard (useEffect mount)
│   ├── components/
│   │   ├── CogniForgeApp.jsx   # MAIN — auth state + routing (do not split carelessly)
│   │   ├── ChatInterface.jsx   # Chat message rendering
│   │   └── AgentTimeline.jsx   # Agent status sidebar
│   ├── hooks/
│   │   └── useAgentSocket.js   # WebSocket hook — wraps all socket logic
│   └── utils/
│       └── errorTracker.js     # Error reporting
├── public/                 # Static assets
└── next.config.js          # API rewrites → backend:8000 (CRITICAL)
```

---

## API Calls — Use the apiUrl Helper

```javascript
// At top of CogniForgeApp.jsx
const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? '';
const apiUrl = (path) => `${API_ORIGIN}${path}`;

// Usage — always use apiUrl(), never hardcode localhost
const response = await fetch(apiUrl('/api/security/login'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
});

// With auth token
const response = await fetch(apiUrl('/api/v1/users/me'), {
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
    },
});
```

**Why no hardcoded localhost?** `next.config.js` rewrites `/api/*` to `http://localhost:8000` — the `apiUrl()` helper respects `NEXT_PUBLIC_API_URL` for production deployments.

---

## RTL Arabic Layout

```jsx
// layout.jsx — already configured
export default function RootLayout({ children }) {
    return (
        <html lang="ar" dir="rtl" suppressHydrationWarning>
            <body suppressHydrationWarning>{children}</body>
        </html>
    );
}

// CSS RTL patterns
.message-container {
    direction: rtl;
    text-align: right;
    font-family: 'Segoe UI', Tahoma, Arial, sans-serif; /* Arabic-friendly */
}

/* For mixed Arabic/French/Latin content */
.mixed-content {
    unicode-bidi: embed;
    direction: rtl;
}

/* Force LTR for code blocks inside RTL */
.message-container pre,
.message-container code {
    direction: ltr;
    text-align: left;
    unicode-bidi: embed;
}
```

---

## KaTeX Math Rendering

```jsx
// Install check — already in package.json:
// "katex": "^0.16.27"
// "rehype-katex": latest
// "remark-math": latest

import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

function MathMessage({ content }) {
    return (
        <ReactMarkdown
            remarkPlugins={[remarkMath]}
            rehypePlugins={[rehypeKatex]}
        >
            {content}
        </ReactMarkdown>
    );
}

// Example content that renders correctly:
// "الجذر التربيعي: $\sqrt{x^2 + y^2}$"
// "معادلة ثانوية: $$ax^2 + bx + c = 0$$"
```

---

## WebSocket Integration

```javascript
// hooks/useAgentSocket.js pattern
import { useEffect, useRef, useCallback } from 'react';

export function useAgentSocket({ token, conversationId, onMessage, onStatus }) {
    const wsRef = useRef(null);

    const connect = useCallback(() => {
        const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/chat/ws`;

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
            // Send auth immediately on connect
            ws.send(JSON.stringify({ type: 'auth', token }));
            onStatus?.('connected');
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage?.(data);
        };

        ws.onclose = () => {
            onStatus?.('disconnected');
            // Auto-reconnect after 2s
            setTimeout(connect, 2000);
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            onStatus?.('error');
        };

        return () => ws.close();
    }, [token, conversationId, onMessage, onStatus]);

    useEffect(() => {
        if (token) return connect();
    }, [token, connect]);

    const sendMessage = useCallback((message) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
                type: 'message',
                content: message,
                conversation_id: conversationId,
            }));
        }
    }, [conversationId]);

    return { sendMessage };
}
```

---

## Hydration Guard Pattern

```jsx
// ClientOnlyApp.jsx — prevents SSR hydration mismatch
"use client";

import { useEffect, useState } from "react";
import CogniForgeApp from "./components/CogniForgeApp";

export default function ClientOnlyApp() {
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    // Returns null on server — renders only after hydration
    if (!mounted) return null;

    return <CogniForgeApp />;
}
```

**Why is this needed?** The app uses `localStorage` for token storage. Next.js SSR runs on the server where `localStorage` doesn't exist — the hydration guard ensures the component only mounts client-side.

---

## Adding a New Page

```jsx
// Create: frontend/app/my-page/page.jsx
import ClientOnlyWrapper from "../ClientOnlyApp"; // reuse hydration guard

export const metadata = {
    title: "My Page — CogniForge",
};

export default function MyPage() {
    return (
        <main>
            <h1>صفحة جديدة</h1>
        </main>
    );
}
```

---

## Common Issues & Fixes

| Issue | Cause | Fix |
|---|---|---|
| `localStorage is not defined` | SSR access | Use hydration guard or `typeof window !== 'undefined'` check |
| API calls return 404 | Missing `next.config.js` rewrite | Never call `localhost:8000` directly — use `apiUrl()` |
| Arabic text renders LTR | Missing `dir="rtl"` | Check layout.jsx or add `direction: rtl` to CSS |
| Math not rendering | Missing CSS import | Add `import 'katex/dist/katex.min.css'` to layout.jsx |
| WebSocket fails in Codespaces | HTTP vs HTTPS mismatch | Use `wss://` when `window.location.protocol === 'https:'` |
| `suppressHydrationWarning` warnings | React hydration mismatch | Already handled — don't remove `suppressHydrationWarning` |
