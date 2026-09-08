/**
 * useRealtimeConnection — WebSocket connection manager
 *
 * ## State Machine (internal — صادق دائماً)
 *
 *   idle → connecting → connected → degraded → reconnecting → offline
 *                                                           ↘ recovered (→ connected)
 *
 * ## مبدأ معماري حاسم (D-WS-FLAP-004 — honest-debounce)
 *
 * الـ Hook يُصدر **حالتين منفصلتين**:
 *
 *   1. `internalState` — الحالة الداخلية الصادقة، تتتبع كل blip فوراً.
 *      تُستخدم في: debug logs, telemetry, الإصلاحات المستقبلية.
 *
 *   2. `state` (= `uiState`) — الحالة الموجَّهة للـ UI. تتأخر قليلاً عن
 *      `internalState` لتجنب flicker على blips قصيرة جداً، لكنها
 *      **لا تكذب** على المستخدم:
 *        - blip < 2 ثانية: UI = "connected" (الأرجح نتعافى — تجنب flicker)
 *        - disconnect 2s..15s: UI = "reconnecting" (الحقيقة الصادقة)
 *        - disconnect > 15s: UI = "offline" (الحقيقة الأصرح)
 *
 * هذا ليس "sticky كذب" — هذا debounce قصير محسوب لتجنب flicker على
 * blips شبكية طبيعية، ثم إظهار الحقيقة الكاملة بعد فترة معقولة.
 *
 * ## Offline Declaration Rules (D-WS-002 + D-WS-FLAP-004)
 *   - الحالة الداخلية: تُعلَن `offline` بعد استنفاد MAX_RETRIES.
 *   - الحالة العامة (UI): تُعلَن `offline` بعد OFFLINE_GRACE_MS متواصل
 *     من فقدان الاتصال بغض النظر عن internal retries.
 *
 * ## Heartbeat
 *   ping/pong كل HEARTBEAT_INTERVAL ms للكشف عن stale connections.
 *   إذا لم يصل pong خلال HEARTBEAT_TIMEOUT ms → إعادة الاتصال.
 */

import { useEffect, useRef, useState, useCallback } from "react";

import { BUILD_VERSION } from "../buildVersion";
import { clientLog } from "../utils/clientLog";

const MAX_BACKOFF = 30000; // أقصى تأخير بين المحاولات (30 ثانية)
// D-WS-FLAP-003 (2026-05-26): زدنا MAX_RETRIES إلى 30 لتفادي إعلان "offline"
// المبكر على شبكات الهاتف المتذبذبة (carrier-NAT يقطع الاتصال مؤقتاً).
const MAX_RETRIES = 30;
const FATAL_CODES = new Set([4401, 4403]);
// D-WS-AUTH-001 (2026-05-26) → D-WS-KICK-001 (ISS-097 — 2026-05-29):
// 4401 لا يُسجِّل الخروج وحده أبداً. المسار الوحيد إلى auth_error هو probe
// HTTP /me يُرجع 401/403 صراحةً (= الـ token ميت حقاً). عدّاد المحاولات
// المنفصل (MAX_FATAL_RETRIES) أُزيل: لا حدّ يُترجَم إلى طرد — فقط نتيجة /me
// القطعية. إعادة الاتصال على 4401-بـ-token-صالح تستخدم عدّاد retries العام.
const REVALIDATION_TIMEOUT_MS = 5000; // مهلة /me probe
// D-WS-FLAP-003: heartbeat كل 45s (كان 25s) — يعطي مساحة لـ proxies بدون إغراق.
// uvicorn --ws-ping-interval 20 يفحص الـ TCP layer تلقائياً.
// ISS-091 (D-WS-HEARTBEAT-002 — 2026-05-27): زدنا HEARTBEAT_TIMEOUT إلى 90s
// (كان 15s). السبب: receive_json في server side محجوب أثناء streaming الـ LLM،
// فلا يُعالَج ping حتى يكتمل البث. إجابات الشرح الطويلة + fallback chain تستغرق
// 30-90s. مع timeout=15s، أي إجابة >60s كانت تُسبب false-disconnect →
// "لا يرد عن الأسئلة" (السؤال يُرسَل لكن الـ WS يُغلق قبل وصول الرد).
// uvicorn --ws-ping-interval 20 يحافظ على الـ TCP alive في كل الأحوال.
const HEARTBEAT_INTERVAL = 45000;
const HEARTBEAT_TIMEOUT = 90000; // كان 15s — يتسامح مع long LLM streams (90s)
// ISS-101 (D-WS-PROXY-002/003): بصمة بناء العميل — تُرسَل في WS URL (?cb=) ويُسجِّلها
// server.js. تُثبت أي نسخة JS يُشغّلها المتصفح فعلاً (للكشف عن bundle قديم مُخبَّأ).
// المصدر الموحَّد في buildVersion.js (يُستخدم أيضاً في فحص إعادة التحميل الذاتي).
const CLIENT_BUILD = BUILD_VERSION;
// D-WS-FLAP-003: لا نُسمِّي الاتصال "reconnecting" إلا بعد فشل حقيقي.
// 1000 = NORMAL_CLOSURE — يحدث عند unmount/cleanup أو إغلاق الـ tab.
// 1001 = GOING_AWAY — يحدث عند navigation.
// لا داعي للـ reconnect على هذه الـ codes إن جاءت من cleanup.
const SILENT_CLOSE_CODES = new Set([1000, 1001]);
// D-WS-FLAP-003: نافذة "اتصال مستقر" — لو الاتصال صمد أكثر من STABLE_THRESHOLD،
// أي close تالٍ يُعتَبر شبكي عابر ونُعيد المحاولة دون إعلان "reconnecting" حالاً.
const STABLE_THRESHOLD_MS = 3000;

// D-WS-AUTH-001 (2026-05-26): دالة probe للتحقق من صلاحية الـ token عبر HTTP.
// نستخدم نفس wsUrl محلولاً إلى http(s) للوصول إلى /api/security/user/me.
// إذا 200 → token صالح، 4401 على WS كان transient.
// إذا 401 → token حقاً منتهي، فعّل auth_error.
// إذا network error → غير قطعي، نعتبره transient (لا نُطرَد).
const revalidateTokenViaHttp = async (wsUrl, token, signal) => {
  if (!token || typeof wsUrl !== "string") return "unknown";
  try {
    // wsUrl: wss://host/api/chat/ws?token=...
    // → https://host/api/security/user/me
    const url = new URL(wsUrl);
    const httpProtocol = url.protocol === "wss:" ? "https:" : "http:";
    const httpUrl = `${httpProtocol}//${url.host}/api/security/user/me`;
    const response = await fetch(httpUrl, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
      signal,
    });
    if (response.ok) return "valid";
    if (response.status === 401 || response.status === 403) return "invalid";
    return "unknown";
  } catch (_err) {
    return "unknown";
  }
};

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
  // ISS-096 (2026-05-28): wsUrl/token/eventNamespace يُخزَّنون في refs حتى
  // connect useCallback لا يتغير عند تغيّرهم → useEffect الرئيسي لا يُعيد
  // التشغيل → لا cleanup → لا إغلاق مفاجئ للـ WebSocket أثناء الدردشة.
  const wsUrlRef = useRef(wsUrl);
  const tokenRef = useRef(token);
  const eventNamespaceRef = useRef(eventNamespace);
  useEffect(() => { wsUrlRef.current = wsUrl; }, [wsUrl]);
  useEffect(() => { tokenRef.current = token; }, [token]);
  useEffect(() => { eventNamespaceRef.current = eventNamespace; }, [eventNamespace]);

  const wsRef = useRef(null);
  const retries = useRef(0);
  // D-WS-AUTH-001 (2026-05-26): عداد منفصل لـ 4401/4403 retries.
  // نُميِّز بين retries عامة (network blips) و retries auth-specific لأن
  // logic كل منهما مختلف (auth يحتاج HTTP probe، network يحتاج backoff فقط).
  const fatalRetries = useRef(0);
  // AbortController لإلغاء HTTP probes عند unmount
  const revalidateAbortRef = useRef(null);
  const [state, setState] = useState("idle");
  // D-WS-FLAP-004 (rev. honest-debounce — 2026-05-26):
  //
  // مبدأ معماري حاسم (طلب المستخدم): الـ UI **لا يكذب**. الحالة الداخلية
  // `state` صادقة دائماً (تتتبع كل blip حقيقي). الـ `uiState` العام
  // فقط يتأخر قليلاً في إظهار الانقطاع لتجنب flicker — لكنه لا يخفي
  // الحقيقة.
  //
  // الفلسفة الصحيحة:
  //   - blip < RECONNECT_VISIBLE_MS (2s): اعرض "متصل" (تجنب flicker)
  //   - disconnect 2s..OFFLINE_GRACE_MS: اعرض "إعادة الاتصال" (الحقيقة)
  //   - disconnect > OFFLINE_GRACE_MS: اعرض "غير متصل" (الحقيقة الأصرح)
  //
  // هكذا الـ UI صادق لكنه ناعم — لا flicker، ولا كذب.
  const [uiState, setUiState] = useState("idle");
  const everConnectedRef = useRef(false);
  const lastConnectedAtRef = useRef(0);
  // timer واحد للترقية من "متصل" → "reconnecting" → "offline" بشكل مدرَّج
  const uiPromotionTimerRef = useRef(null);
  const mountedRef = useRef(true);
  const reconnectTimeoutRef = useRef(null);
  const pendingQueue = useRef([]);
  const connectionIdRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const heartbeatTimeoutRef = useRef(null);
  // D-WS-FLAP-003: متى آخر مرة فتحنا الاتصال بنجاح (Date.now()).
  // يُستخدم للكشف عن close سريع غير طبيعي (proxy idle-kill vs network blip).
  const openedAtRef = useRef(0);
  // D-WS-FLAP-003: timer للـ "stable" تأخير state="reconnecting" لـ 500ms — لو
  // اتصلنا فوراً من جديد لا يرى المستخدم أي وميض.
  const stateDebounceRef = useRef(null);

  // D-WS-FLAP-004 (honest-debounce):
  // - RECONNECT_VISIBLE_MS: بعد كم ms من الفقد يصبح UI صريحاً عن الـ reconnect.
  //   2 ثانية كافية لتجنب flicker على blips قصيرة لكن سريعة بما يكفي ليعرف
  //   المستخدم أن هناك مشكلة فعلية.
  // - OFFLINE_GRACE_MS: بعد كم ms من الفقد المتواصل يصبح UI صريحاً عن الـ offline.
  //   15 ثانية تكفي لكي تنجح عدة محاولات reconnect عادة، لكنها ليست طويلة جداً.
  const RECONNECT_VISIBLE_MS = 2000;
  const OFFLINE_GRACE_MS = 15000;

  // إلغاء أي promotion مجدوَل (نُستدعى عند `connected`).
  const cancelUiPromotion = useCallback(() => {
    if (uiPromotionTimerRef.current) {
      clearTimeout(uiPromotionTimerRef.current);
      uiPromotionTimerRef.current = null;
    }
  }, []);

  // جدولة promotion مدرَّج: "connected" → "reconnecting" بعد 2s → "offline" بعد 15s.
  // لو رجع internal state إلى "connected" قبل أي مرحلة، الـ timer يُلغى.
  const scheduleUiPromotionForDisconnect = useCallback(() => {
    cancelUiPromotion();
    // المرحلة 1: بعد RECONNECT_VISIBLE_MS، أظهر "reconnecting" (الحقيقة).
    uiPromotionTimerRef.current = setTimeout(() => {
      if (!mountedRef.current) return;
      // فحص: ربما عاد internal state إلى connected في هذه اللحظة.
      // ولا نُظهر "reconnecting" لو internal لم يعد منقطعاً.
      const stillDisconnected = !wsRef.current ||
        (wsRef.current.readyState !== WebSocket.OPEN);
      if (!stillDisconnected) return;
      setUiState("reconnecting");
      // المرحلة 2: بعد OFFLINE_GRACE_MS من الفقد الأصلي، أظهر "offline".
      uiPromotionTimerRef.current = setTimeout(() => {
        if (!mountedRef.current) return;
        const stillOff = !wsRef.current ||
          (wsRef.current.readyState !== WebSocket.OPEN);
        if (!stillOff) return;
        console.warn("[WS] offline grace expired — showing offline UI");
        setUiState("offline");
      }, OFFLINE_GRACE_MS - RECONNECT_VISIBLE_MS);
    }, RECONNECT_VISIBLE_MS);
  }, [cancelUiPromotion]);

  // مزامنة uiState مع state — لكن بصدق: تأخير قصير لتجنب flicker، ثم الحقيقة.
  useEffect(() => {
    if (!mountedRef.current) return;

    // auth_error دائماً يطغى — هذا fatal حقيقي.
    if (state === "auth_error") {
      cancelUiPromotion();
      setUiState("auth_error");
      return;
    }

    // قبل أول اتصال ناجح — اعرض الحالة الحقيقية فوراً (بدون كذب).
    if (!everConnectedRef.current) {
      cancelUiPromotion();
      setUiState(state);
      return;
    }

    // بعد أول اتصال:
    //   - connected/recovered → "connected" فوراً، ألغِ أي promotion.
    if (state === "connected" || state === "recovered") {
      cancelUiPromotion();
      setUiState("connected");
      return;
    }

    //   - disconnect (reconnecting/degraded/connecting/offline): جدول promotion
    //     مدرَّج. خلال أول 2 ثانية يبقى UI = "متصل" (debounce لتجنب flicker)،
    //     ثم "reconnecting" (الحقيقة)، ثم "offline" (الحقيقة الأصرح).
    if (
      state === "reconnecting" ||
      state === "degraded" ||
      state === "connecting" ||
      state === "offline"
    ) {
      // لا يُلغي promotion موجوداً (لو كانت سلسلة من disconnect states).
      if (!uiPromotionTimerRef.current) {
        scheduleUiPromotionForDisconnect();
      }
      return;
    }
  }, [state, cancelUiPromotion, scheduleUiPromotionForDisconnect]);

  if (connectionIdRef.current === null) {
    connectionIdRef.current =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }

  // إيقاف heartbeat
  const stopHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
      heartbeatTimeoutRef.current = null;
    }
  }, []);

  // بدء heartbeat — ping/pong للكشف عن stale connections
  const startHeartbeat = useCallback((ws) => {
    stopHeartbeat();
    heartbeatIntervalRef.current = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        stopHeartbeat();
        return;
      }
      try {
        ws.send(JSON.stringify({ type: "ping" }));
      } catch {
        stopHeartbeat();
        return;
      }
      // ISS-101 (D-WS-PROXY-002 — 2026-05-30): الـ heartbeat لم يعد يُغلق الاتصال.
      //
      // الكارثة المُصلَحة: كان `ws.close(1001,"heartbeat_timeout")` يقطع اتصالات
      // حيّة-لكن-بطيئة (دور طويل، أو pong تأخّر عبر سلسلة الـ proxy) → reconnect
      // متكرر (close 1001) → إجابات مقطوعة + تأرجح. تشخيص حيّ أظهر اتصالات تُغلق
      // بـ 1001 بعد session_ready/conversation_init مباشرة وقبل deltas.
      //
      // الكشف عن الاتصال الميت فعلاً مضمون من طبقتين أدنى: uvicorn protocol
      // ping/pong (`--ws-ping-interval 20 --ws-ping-timeout 30`) يُغلق نصف-المفتوح
      // من جهة الخادم، والمتصفح يُطلق onclose(1006) عند موت TCP → reconnect صحيح.
      // لذا نكتفي هنا بـ ping تطبيقي (يُبقي proxies/NAT دافئة، والخادم يردّ pong
      // فيُلغي أي مؤقّت عبر D-WS-FLAP-005) — بلا إغلاق استباقي.
      heartbeatTimeoutRef.current = setTimeout(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          console.info(
            "[WS] heartbeat: no app-level pong within window — keeping connection " +
              "(uvicorn protocol ping + browser will recycle if truly dead)"
          );
        }
      }, HEARTBEAT_TIMEOUT);
    }, HEARTBEAT_INTERVAL);
  }, [stopHeartbeat]);

  const connect = useCallback(() => {
    // ISS-096: اقرأ من refs — لا closure على wsUrl/token/eventNamespace.
    const wsUrl = wsUrlRef.current;
    const token = tokenRef.current;
    if (!wsUrl || !token) return;
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;

    // D-WS-002: "reconnecting" بدلاً من "offline" أثناء المحاولات
    setState(retries.current > 0 ? "reconnecting" : "connecting");

    try {
        const wsUrlObj = new URL(wsUrl);

        // ISS-WS-001: token يُرسَل عبر query param فقط.
        // الكود القديم كان يُرسله في ["jwt", token] subprotocol —
        // Codespaces edge proxy وcarrier-NAT وBrave Mobile تحذفه → 4401.
        // query param يعمل عبر كل الشبكات لأنه جزء من URL وليس header.
        if (token) {
            wsUrlObj.searchParams.set("token", token);
        }
        if (!wsUrlObj.searchParams.has("session_id")) {
            wsUrlObj.searchParams.set("session_id", connectionIdRef.current);
        }
        // ISS-101: بصمة البناء — server.js يُسجِّلها لإثبات نسخة JS المُحمَّلة فعلاً.
        wsUrlObj.searchParams.set("cb", CLIENT_BUILD);

        // Log auth transport mode بدون تسريب token value
        const authMode = token ? "query_param" : "none";
        const safeUrl = wsUrlObj.toString().replace(/token=[^&]+/, "token=[REDACTED]");
        console.info(
            `[WS] connecting auth_mode=${authMode} attempt=${retries.current + 1}/${MAX_RETRIES} url=${safeUrl}`
        );

        // لا subprotocols — يُبسِّط الـ handshake ويتجنب رفض proxies
        const ws = new WebSocket(wsUrlObj.toString());
        wsRef.current = ws;

        ws.onopen = () => {
          if (mountedRef.current) {
            // D-WS-FLAP-003: ألغِ أي debounce timer من المحاولة السابقة —
            // إن كنّا في نافذة "reconnecting" قصيرة ولم نُظهر الحالة بعد،
            // الآن نُلغي ذلك ونبقى على "connected".
            if (stateDebounceRef.current) {
              clearTimeout(stateDebounceRef.current);
              stateDebounceRef.current = null;
            }

            // D-WS-FLAP-003: سجّل وقت الفتح الناجح — يُستخدم في onclose للتمييز.
            openedAtRef.current = Date.now();
            // D-WS-FLAP-004: علِّم أنّ الاتصال نجح مرة على الأقل — UI sync useEffect
            // سيرى هذا ويُحدِّث uiState إلى "connected" فوراً.
            everConnectedRef.current = true;
            lastConnectedAtRef.current = Date.now();
            // D-WS-FLAP-004 (REGRESSION FIX 2026-05-26): ألغِ UI promotion timer
            // المجدوَل — تعافينا، لا حاجة لإظهار "reconnecting".
            // كان هذا السطر يشير إلى `offlineGraceTimerRef` المحذوف بعد refactor،
            // ما يُسبب ReferenceError ويُحطِّم الـ onopen handler — وبالتالي
            // "متصل" لم تظهر أبداً للمستخدم.
            if (uiPromotionTimerRef.current) {
              clearTimeout(uiPromotionTimerRef.current);
              uiPromotionTimerRef.current = null;
            }

            const wasReconnect = retries.current > 0;
            retries.current = 0;
            // D-WS-AUTH-001: reset عداد 4401 — اتصال ناجح يُلغي أي شك في الـ token.
            fatalRetries.current = 0;
            // ألغِ أي probe HTTP جاري (مش محتاج لو الاتصال نجح)
            if (revalidateAbortRef.current) {
              revalidateAbortRef.current.abort();
              revalidateAbortRef.current = null;
            }
            setState(wasReconnect ? "recovered" : "connected");
            // ISS-101 (D-WS-KICK-DIAG): breadcrumb — اتصال ناجح (مع/بدون reconnect).
            clientLog("ws_open", { was_reconnect: wasReconnect });

            // بعد recovery → انتقل إلى connected بعد لحظة قصيرة للـ UI feedback
            if (wasReconnect) {
              setTimeout(() => {
                if (mountedRef.current) setState("connected");
              }, 500);
            }

            // بدء heartbeat للكشف عن stale connections
            startHeartbeat(ws);

            // Flush pending messages
            if (pendingQueue.current.length > 0) {

                while (pendingQueue.current.length > 0) {
                    const msg = pendingQueue.current.shift();
                    try { ws.send(JSON.stringify(msg)); } catch { /* ignore */ }
                }
            }
          }
        };

        // ISS-STREAM-004: Delta batching via requestAnimationFrame
        // Problem: 400+ delta chunks arrive in <4s → 400+ dispatchEvent calls →
        //          400+ React setState calls → machine-gun re-renders that freeze UI.
        // Fix: buffer delta chunks and flush them in a single batch per animation frame.
        //      Non-delta events (conversation_init, persisted, error, etc.) are dispatched
        //      immediately to preserve correct lifecycle ordering.
        const deltaBuffer = [];
        let rafPending = false;

        const flushDeltaBuffer = () => {
          rafPending = false;
          if (!mountedRef.current || deltaBuffer.length === 0) return;

          // ISS-DELTA-BUG-001 (2026-05-28): حفظ baseEvent قبل splice —
          // deltaBuffer.splice(0) يُفرغ المصفوفة فوراً، فـ deltaBuffer[0] بعدها = undefined.
          // النتيجة القديمة: baseEvent={} → mergedEvent بدون _connection_id/_event_namespace
          // → useAgentSocket يستقبل event بدون metadata → قد يُرفض أو يُعالَج بشكل خاطئ.
          const baseEvent = deltaBuffer[deltaBuffer.length - 1] || {};

          // Merge all buffered delta content into a single chunk
          const merged = deltaBuffer.splice(0).reduce((acc, ev) => {
            const content = ev.payload?.content;
            if (typeof content === 'string') acc += content;
            return acc;
          }, '');

          if (!merged) return;

          // Use the last buffered event as the envelope, replace content with merged
          const mergedEvent = {
            ...baseEvent,
            type: 'assistant_delta',
            payload: { ...(baseEvent.payload || {}), content: merged },
          };

          window.dispatchEvent(new CustomEvent('agent:event', { detail: mergedEvent }));
          window.dispatchEvent(new CustomEvent(`agent:event:${eventNamespaceRef.current}`, { detail: mergedEvent }));
        };

        const scheduleDeltaFlush = () => {
          if (!rafPending) {
            rafPending = true;
            requestAnimationFrame(flushDeltaBuffer);
          }
        };

        ws.onmessage = (event) => {
          if (!mountedRef.current) return;

          // ISS-098 (D-WS-FLAP-005 — 2026-05-29): أي رسالة واردة تُثبت أن
          // الاتصال حيّ، فتُلغي timeout الـ heartbeat — ليس pong فقط.
          //
          // الجذر: الـ backend receive loop محجوب أثناء `await stream_task`
          // طوال بثّ الإجابة، فلا يستطيع قراءة ping العميل والردّ بـ pong.
          // مع زمن Supabase + إجابة طويلة، يتجاوز الدور الواحد
          // HEARTBEAT_TIMEOUT (90s) → close(1001) كاذب → reconnect →
          // الإجابة الجارية تضيع ("لا يرد عن الأسئلة" للأسئلة الطويلة).
          // تدفّق الـ deltas نفسه دليل قاطع على أن الاتصال حيّ، لذا نُلغي
          // الـ timeout عند أي رسالة. (الاتصال الميت فعلاً لا يُرسل شيئاً
          // فيبقى الـ timeout يعمل ويُطلق reconnect بشكل صحيح.)
          if (heartbeatTimeoutRef.current) {
            clearTimeout(heartbeatTimeoutRef.current);
            heartbeatTimeoutRef.current = null;
          }

          // معالجة pong من heartbeat — لا نُعالجه كبيانات
          if (typeof event.data === "string" && event.data.includes('"type":"pong"')) {
            return;
          }

          // Bug A fix: detect HTML error pages (Next.js DevTools 500 bleed).
          // When the backend crashes, Next.js dev server may intercept the 500
          // and stream back a raw HTML page containing <nextjs-portal> or
          // <!DOCTYPE html>. Guard here before JSON.parse so the HTML never
          // reaches the chat renderer as text content.
          if (typeof event.data === "string") {
            const trimmed = event.data.trimStart();
            if (trimmed.startsWith("<") || trimmed.startsWith("<!DOCTYPE")) {
              console.error("[WS] Received HTML instead of JSON — backend 500 error page intercepted by Next.js DevTools. Suppressing HTML bleed.", event.data.slice(0, 200));
              window.dispatchEvent(
                new CustomEvent("agent:notification", {
                  detail: { level: "error", message: "حدث خطأ في الخادم. يرجى المحاولة مرة أخرى." },
                })
              );
              window.dispatchEvent(
                new CustomEvent("agent:event", {
                  detail: {
                    type: "assistant_final",
                    payload: { content: "" },
                    _connection_id: connectionIdRef.current,
                    _event_namespace: eventNamespaceRef.current,
                  },
                })
              );
              return;
            }
          }

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
              _event_namespace: eventNamespaceRef.current,
            };

            const eventType = data?.type;
            const isDelta = eventType === 'delta' || eventType === 'assistant_delta';

            if (isDelta) {
              // Buffer delta events — flush once per animation frame (~16ms)
              deltaBuffer.push(enrichedData);
              scheduleDeltaFlush();
            } else {
              // Flush any pending deltas before dispatching lifecycle events
              // to preserve correct ordering (e.g. deltas before assistant_final)
              if (deltaBuffer.length > 0) flushDeltaBuffer();

              window.dispatchEvent(
                new CustomEvent("agent:event", {
                  detail: enrichedData,
                })
              );
              window.dispatchEvent(
                new CustomEvent(`agent:event:${eventNamespaceRef.current}`, {
                  detail: enrichedData,
                })
              );
            }
          } catch (e) {
            console.warn("Failed to parse WebSocket message:", e);
          }
        };

        ws.onerror = (err) => {
          if (mountedRef.current) {
              // degraded وليس offline — onclose سيُقرِّر ما إذا كان يجب إعادة الاتصال
              setState("degraded");
          }
          console.warn("[WS] error", {
            url: ws.url,
            readyState: ws.readyState,
            error: err?.message || "unknown",
          });
        };

        ws.onclose = (e) => {
          if (!mountedRef.current) {
            // الـ component unmounted أو الـ effect cleanup قيد التنفيذ — تجاهل تماماً.
            return;
          }

          // D-WS-FLAP-003: لو الـ ws الذي أُغلق ليس wsRef.current الحالي،
          // فهذا close لاتصال قديم (race condition من إعادة render). تجاهل.
          if (wsRef.current && wsRef.current !== ws) {
            console.info(
              "[WS] ignoring close of stale ws (replaced by newer connection)",
              { code: e.code, reason: e.reason }
            );
            return;
          }

          wsRef.current = null;
          stopHeartbeat();

          // D-WS-FLAP-003: قياس مدة الاتصال — يفرّق بين close فوري وعابر.
          const sessionMs = openedAtRef.current
            ? Date.now() - openedAtRef.current
            : 0;
          const wasStable = sessionMs >= STABLE_THRESHOLD_MS;

          console.warn("[WS] closed", {
            url: ws.url,
            code: e.code,
            reason: e.reason,
            wasClean: e.wasClean,
            session_ms: sessionMs,
            was_stable: wasStable,
          });
          // ISS-101 (D-WS-KICK-DIAG): breadcrumb — يُسجِّل كل إغلاق (كوده + المدة)
          // ليُظهر السجل التسلسل الكامل (connect → close → reconnect) المؤدّي للطرد،
          // لا الحدث الأخير فقط. حاسم لتشخيص الطرد على الجوال بلا devtools.
          clientLog("ws_close", {
            code: e.code,
            reason: String(e.reason || "").slice(0, 60),
            session_ms: sessionMs,
            attempt: retries.current,
          });

          // D-WS-AUTH-001 (2026-05-26) → D-WS-KICK-001 (ISS-097): 4401/4403
          // ─────────────────────────────────────────────────────────────────
          // 4401 قد يكون transient في بيئات mobile/Codespaces:
          //   - DB lag → db.get(User) returns None / يرمي استثناء
          //   - clock skew بين client و server
          //   - Codespaces proxy / carrier-NAT حذف auth header
          //   - خلل WS من جهة الخادم (race، إغلاق مفاجئ)
          //
          // الـ flow (D-WS-KICK-001 — لا حدّ يُترجَم إلى طرد):
          //   1. probe HTTP /me لتأكيد صلاحية الـ token:
          //      - 401/403 → الـ token ميت حقاً → fire auth_error (المسار الوحيد)
          //      - 200 (valid) أو network/unknown → الـ token سليم → أعد الاتصال
          //   2. لا تسجيل خروج أبداً ما دام /me لا يُؤكِّد البطلان.
          if (FATAL_CODES.has(e.code)) {
            fatalRetries.current += 1;

            console.warn("[WS] Auth-related close — investigating", {
              code: e.code,
              reason: e.reason,
              attempt: fatalRetries.current,
            });

            // ─────────────────────────────────────────────────────────────────
            // D-WS-KICK-001 (ISS-097 — 2026-05-29): WS 4401 لا يُسجِّل الخروج وحده.
            // ─────────────────────────────────────────────────────────────────
            // الكارثة المُشخَّصة: الكود القديم كان يُطلق `agent:auth_error`
            // (→ logout → "محادثة جديدة") بعد MAX_FATAL_RETRIES إغلاقات 4401
            // *بدون* تأكيد أن الـ token فعلاً منتهٍ. مع FATAL_RETRY_DELAY_MS=2s،
            // كان ذلك طرداً خلال ~6-8 ثوانٍ — حتى عندما يكون الـ token صالحاً
            // تماماً. أي خلل WS من جهة الخادم (db.get transient، blip شبكي،
            // race) كان يُترجَم إلى تسجيل خروج كارثي.
            //
            // القاعدة الجديدة (لا تُكسر بدون ADR): المسار **الوحيد** إلى
            // `agent:auth_error` هو probe HTTP `/me` يُرجع 401/403 صراحةً
            // (= الـ token ميت حقاً). أي نتيجة أخرى (200 = صالح، أو
            // network/unknown = الخادم غير قابل للوصول) → نُبقي الجلسة
            // ونُعيد الاتصال بـ exponential backoff. لا طرد أبداً ما دام
            // الـ token صالحاً.
            //
            // إذا انتهى الـ token حقاً (بعد 8 ساعات) → /me يُرجع 401 → طرد
            // نظيف (سلوك صحيح). وحتى حينها، FIX-B يستعيد آخر محادثة بعد
            // إعادة الدخول فلا يفقد المستخدم سياقه.
            if (revalidateAbortRef.current) {
              revalidateAbortRef.current.abort();
            }
            const abortCtl =
              typeof AbortController !== "undefined" ? new AbortController() : null;
            revalidateAbortRef.current = abortCtl;
            const timeoutId = setTimeout(() => {
              if (abortCtl) abortCtl.abort();
            }, REVALIDATION_TIMEOUT_MS);

            // إعادة محاولة transient موحَّدة: backoff تصاعدي عبر عدّاد retries
            // العام (لا عدّاد fatal منفصل) — فإن ظل الخادم 4401 إلى ما لا نهاية
            // مع token صالح، نصل أخيراً إلى "offline" (الخادم معطّل) لا
            // "auth_error" (الجلسة منتهية). هذان حدثان مختلفان تماماً.
            const retryTransientAuth = (probe) => {
              if (!mountedRef.current) return;
              retries.current += 1;
              if (retries.current >= MAX_RETRIES) {
                console.error(
                  `[WS] 4401 persisted ${MAX_RETRIES}× with valid/unknown token — ` +
                    `server unreachable, declaring offline (NOT auth_error).`
                );
                setState("offline");
                return;
              }
              setState(retries.current <= 1 ? "degraded" : "reconnecting");
              if (typeof window !== "undefined") {
                window.dispatchEvent(
                  new CustomEvent("agent:transient_auth_warning", {
                    detail: { code: e.code, attempt: retries.current, probe },
                  })
                );
              }
              const delay = Math.min(Math.pow(2, retries.current - 1) * 500, MAX_BACKOFF);
              const jitter = Math.floor(Math.random() * 500);
              clearTimeout(reconnectTimeoutRef.current);
              reconnectTimeoutRef.current = setTimeout(connect, delay + jitter);
            };

            clientLog("ws_fatal_close", { code: e.code, reason: String(e.reason || "").slice(0, 80) });
            revalidateTokenViaHttp(wsUrl, token, abortCtl?.signal)
              .then((result) => {
                clearTimeout(timeoutId);
                if (!mountedRef.current) return;
                console.info("[WS] Token revalidation result:", result);
                clientLog("ws_revalidate_result", { code: e.code, result });

                if (result === "invalid") {
                  // المسار الوحيد للطرد: /me أكّد أن الـ token ميت حقاً.
                  console.error("[WS] Token confirmed invalid via /me — escalating to auth_error.");
                  setState("auth_error");
                  if (typeof window !== "undefined") {
                    window.dispatchEvent(
                      new CustomEvent("agent:auth_error", {
                        detail: { code: e.code, reason: "token_invalid_confirmed_via_http" },
                      })
                    );
                  }
                  return;
                }

                // result === "valid" أو "unknown" → الـ token سليم، الخلل من
                // الخادم → أعد الاتصال، لا تطرد.
                console.info(
                  `[WS] 4401 treated as transient (probe=${result}) — token NOT dead, reconnecting.`
                );
                retryTransientAuth(result);
              })
              .catch(() => {
                clearTimeout(timeoutId);
                if (!mountedRef.current) return;
                // probe أُلغي أو فشل → unknown → أعد الاتصال (لا طرد).
                console.info("[WS] Token probe aborted/failed — treating as transient (no logout).");
                retryTransientAuth("unknown");
              });

            // مُهم: نُرجع هنا لأن probe + reconnect سيتمان async.
            return;
          }

          // D-WS-AUTH-001: لو وصلنا هنا، الـ close ليس auth-related.
          // أعد ضبط fatalRetries (نجاح اتصال غير-auth).
          fatalRetries.current = 0;

          // D-WS-FLAP-003: close codes "صامتة" لا تستحق إعلان reconnecting.
          // 1000/1001 من cleanup/navigation. نُعيد المحاولة لكن لا نُحدِّث الـ UI.
          const silentClose = SILENT_CLOSE_CODES.has(e.code);

          retries.current += 1;

          // D-WS-002: لا يُعلَن عن Offline إلا بعد استنفاد جميع المحاولات
          if (retries.current >= MAX_RETRIES) {
            console.error(
              `[WS] Exhausted ${MAX_RETRIES} reconnect attempts — declaring offline. ` +
                `last_close_code=${e.code} auth_mode=${token ? "query_param" : "none"}`
            );
            setState("offline");
            return; // لا إعادة اتصال تلقائية — المستخدم يحتاج reload
          }

          // D-WS-FLAP-003: لو الاتصال كان مستقراً (>3s) أو close صامت،
          // أبقِ الـ UI على "متصل" حتى آخر لحظة. الـ debounce يمنع flicker:
          // لو نجحنا في الاتصال خلال 500ms، المستخدم لن يرى "إعادة الاتصال".
          const showReconnectingState = () => {
            if (mountedRef.current) setState("reconnecting");
          };

          if (silentClose || wasStable) {
            // أجِّل إعلان "reconnecting" لـ 500ms — لو نجح الـ retry قبلها لا flicker.
            clearTimeout(stateDebounceRef.current);
            stateDebounceRef.current = setTimeout(showReconnectingState, 500);
          } else {
            // اتصال فشل سريعاً (<3s) ولم يكن silent — أعلِنها فوراً.
            setState("reconnecting");
          }

          // Exponential backoff مع jitter
          const delay = Math.min(Math.pow(2, retries.current - 1) * 500, MAX_BACKOFF);
          const jitter = Math.floor(Math.random() * 500);

          console.info(
            `[WS] Reconnecting in ${delay + jitter}ms (attempt ${retries.current}/${MAX_RETRIES})`
          );
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = setTimeout(connect, delay + jitter);
        };
    } catch (err) {
        console.warn("[WS] Connection failed:", err);
        retries.current += 1;

        if (!mountedRef.current) return;

        // D-WS-002: لا offline إلا بعد exhaustion
        if (retries.current >= MAX_RETRIES) {
            setState("offline");
            return;
        }

        setState("reconnecting");
        const delay = Math.min(Math.pow(2, retries.current - 1) * 500, MAX_BACKOFF);
        const jitter = Math.floor(Math.random() * 500);
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = setTimeout(connect, delay + jitter);
    }
  // ISS-096: wsUrl/token/eventNamespace مُزالة من dependencies — تُقرأ من refs.
  // هذا يمنع إعادة إنشاء connect عند كل تغيير في wsUrl/token → لا cleanup → لا قطع.
  }, [startHeartbeat, stopHeartbeat]);

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
      stopHeartbeat();
      if (wsRef.current) {
        wsRef.current.close(1000, "component_unmount");
        wsRef.current = null;
      }
      clearTimeout(reconnectTimeoutRef.current);
      // D-WS-FLAP-003: نظِّف debounce timer كذلك.
      if (stateDebounceRef.current) {
        clearTimeout(stateDebounceRef.current);
        stateDebounceRef.current = null;
      }
      // D-WS-FLAP-004 (honest-debounce): نظِّف UI promotion timer.
      if (uiPromotionTimerRef.current) {
        clearTimeout(uiPromotionTimerRef.current);
        uiPromotionTimerRef.current = null;
      }
      // D-WS-AUTH-001: ألغِ أي HTTP /me probe جاري.
      if (revalidateAbortRef.current) {
        try {
          revalidateAbortRef.current.abort();
        } catch (_e) {
          /* abort never throws but be safe */
        }
        revalidateAbortRef.current = null;
      }
    };
  }, [connect, stopHeartbeat]);

  // ISS-096: عند تغيير wsUrl (null → URL حقيقي عند أول render في browser)،
  // أو عند تغيير token، نُحاول الاتصال إذا لم يكن هناك اتصال قائم.
  // هذا يُعوِّض عن إزالة wsUrl/token من dependencies connect.
  useEffect(() => {
    if (wsUrl && token && mountedRef.current) {
      if (!wsRef.current ||
          (wsRef.current.readyState !== WebSocket.OPEN &&
           wsRef.current.readyState !== WebSocket.CONNECTING)) {
        connect();
      }
    }
  }, [wsUrl, token, connect]);

  // D-WS-FLAP-004 (honest-debounce): نُرجع uiState للـ UI لكن مع الحفاظ على
  // الصدق — uiState يتأخر قليلاً عن state (لتجنب flicker) لكنه لا يكذب:
  //   - blip < 2s: UI = "متصل" (debounce قصير، الأرجح أن نتعافى)
  //   - disconnect 2s..15s: UI = "reconnecting" (الحقيقة الصادقة)
  //   - disconnect > 15s: UI = "offline" (الحقيقة الأصرح)
  // الحالة الداخلية `state` تبقى مكشوفة عبر `internalState` لمَن يحتاج
  // الحقيقة الفورية (debug logs, telemetry, إلخ).
  return { state: uiState, internalState: state, sendMessage };
}
