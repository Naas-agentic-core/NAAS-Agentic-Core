import { useEffect, useRef, useState, useCallback } from "react";

const MAX_BACKOFF = 10000;
const FATAL_CODES = new Set([4401, 4403]);

const parseAssistantErrorEnvelope = (rawData) => {
  if (typeof rawData !== "string") return null;
  const trimmed = rawData.trim();
  if (!trimmed.startsWith("{")) return null;

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed?.type === "assistant_error") {
      return parsed?.payload?.content || "Unknown assistant error";
    }
  } catch (_error) {
    return null;
  }

  return null;
};

/**
 * Hook to manage a robust WebSocket connection.
 * @param {string} wsUrl - The WebSocket URL.
 * @param {string} token - The authentication token.
 * @returns {{ state: string, sendMessage: (data: any) => void }}
 */
export function useRealtimeConnection(wsUrl, token, eventNamespace = "default") {
  const wsRef = useRef(null);
  const retries = useRef(0);
  const [state, setState] = useState("idle");
  const mountedRef = useRef(true);
  const reconnectTimeoutRef = useRef(null);
  const pendingQueue = useRef([]);
  const connectionIdRef = useRef(
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`
  );

  const connect = useCallback(() => {
    if (!wsUrl || !token) return;
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;

    setState("connecting");

    try {
        const wsUrlObj = new URL(wsUrl);
        wsUrlObj.searchParams.append("token", token);
        const ws = new WebSocket(wsUrlObj.toString(), ["jwt", token]);
        wsRef.current = ws;

        ws.onopen = () => {
          if (mountedRef.current) {
            retries.current = 0;
            setState("connected");

            // Flush pending messages
            if (pendingQueue.current.length > 0) {
                console.log(`Flushing ${pendingQueue.current.length} pending messages`);
                while (pendingQueue.current.length > 0) {
                    const msg = pendingQueue.current.shift();
                    ws.send(JSON.stringify(msg));
                }
            }
          }
        };

        ws.onmessage = (event) => {
          if (!mountedRef.current) return;

          const directAssistantError = parseAssistantErrorEnvelope(event.data);
          if (directAssistantError) {
            window.dispatchEvent(
              new CustomEvent("agent:notification", {
                detail: { level: "error", message: String(directAssistantError) },
              })
            );
            return;
          }

          try {
            const data = JSON.parse(event.data);
            const enrichedData = {
              ...data,
              _connection_id: connectionIdRef.current,
              _event_namespace: eventNamespace,
            };
            // Broadcast agent events
            window.dispatchEvent(
              new CustomEvent("agent:event", {
                detail: enrichedData,
              })
            );
            window.dispatchEvent(
              new CustomEvent(`agent:event:${eventNamespace}`, {
                detail: enrichedData,
              })
            );
          } catch (e) {
            console.warn("Failed to parse WebSocket message:", e);
          }
        };

        ws.onerror = () => {
          if (mountedRef.current) {
              setState("degraded");
          }
          console.warn("[WS] error", {
            url: ws.url,
            readyState: ws.readyState, // 0..3
          });
        };

        ws.onclose = (e) => {
          if (mountedRef.current) {
             wsRef.current = null;

             console.warn("[WS] closed", {
               url: ws.url,
               code: e.code,
               reason: e.reason,
               wasClean: e.wasClean,
               readyState: ws.readyState,
             });

             // Check for fatal auth errors
             if (FATAL_CODES.has(e.code)) {
                 console.warn("Fatal auth error, stopping reconnection:", e.code);
                 setState("auth_error");
                 return; // STOP reconnection
             }

             setState("offline");

             const delay = Math.min(
               2 ** retries.current * 500,
               MAX_BACKOFF
             );

             const jitter = Math.floor(Math.random() * 200);

             retries.current += 1;
             clearTimeout(reconnectTimeoutRef.current);
             reconnectTimeoutRef.current = setTimeout(connect, delay + jitter);
          }
        };
    } catch (err) {
        console.warn("WebSocket connection failed:", err);
        if (mountedRef.current) setState("offline");

        const delay = Math.min(
            2 ** retries.current * 500,
            MAX_BACKOFF
        );
        retries.current += 1;
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(connect, delay);
    }
  }, [wsUrl, token, eventNamespace]);

  const sendMessage = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    } else {
      console.warn("WebSocket is not connected. Queuing message.", data);
      pendingQueue.current.push(data);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (wsRef.current) wsRef.current.close();
      clearTimeout(reconnectTimeoutRef.current);
    };
  }, [connect]);

  return { state, sendMessage };
}
