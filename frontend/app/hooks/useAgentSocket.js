import { useState, useRef, useCallback, useEffect } from 'react';
import { errorTracker } from '../utils/errorTracker';
import { useRealtimeConnection } from './useRealtimeConnection';

const isBrowser = typeof window !== 'undefined';
const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? '';
const WS_ORIGIN = process.env.NEXT_PUBLIC_WS_URL ?? '';

const resolveWebSocketProtocol = (protocol) => {
    if (protocol === 'https:') return 'wss:';
    if (protocol === 'http:') return 'ws:';
    if (protocol === 'wss:' || protocol === 'ws:') return protocol;
    return 'ws:';
};

const getWsBase = () => {
    if (!isBrowser) return '';
    const configuredOrigin = WS_ORIGIN || API_ORIGIN;
    if (configuredOrigin) {
        try {
            const parsed = new URL(configuredOrigin);
            const wsProtocol = resolveWebSocketProtocol(parsed.protocol);
            return `${wsProtocol}//${parsed.host}`;
        } catch (error) {
            errorTracker.reportError(error, { message: 'Invalid WebSocket base configuration' });
            return '';
        }
    }

    // Warn if falling back in production
    if (process.env.NODE_ENV === 'production') {
        console.warn('CRITICAL: NEXT_PUBLIC_WS_URL or NEXT_PUBLIC_API_URL is missing in production. Falling back to window.location, which may cause connection failures.');
    }

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const hostname = window.location.hostname;
    const port = window.location.port;

    // Smart fallback: if we are on port 3000 (standard Next.js), assume backend is on port 8000
    // This fixes local production builds or direct access bypassing Nginx where backend is on default port
    if (port === '3000') {
         return `${protocol}://${hostname}:8000`;
    }

    const host = window.location.host;
    return `${protocol}://${host}`;
};

const buildWebSocketUrlSafe = (baseUrl, endpoint, token) => {
    try {
        const wsUrl = new URL(endpoint, baseUrl);
        // Token is passed in header/protocol by useRealtimeConnection.
        // REMOVED query param appending to prevent "double method" drift.
        return wsUrl.toString();
    } catch (error) {
        errorTracker.reportError(error, { message: 'Invalid WebSocket URL parts' });
        return '';
    }
};

const generateId = () => {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    return Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
};

const parseNestedAssistantError = (value) => {
    if (typeof value !== 'string') return null;
    const trimmed = value.trim();
    if (!trimmed.startsWith('{')) return null;

    try {
        const parsed = JSON.parse(trimmed);
        if (parsed && parsed.type === 'assistant_error') {
            const content = parsed?.payload?.content;
            return typeof content === 'string' && content.trim() ? content : 'Unknown assistant error';
        }
    } catch (_error) {
        return null;
    }

    return null;
};

const notifyAgentError = (message) => {
    if (typeof window === 'undefined') return;
    window.dispatchEvent(
        new CustomEvent('agent:notification', {
            detail: {
                level: 'error',
                message,
            },
        })
    );
};

const computeOverlapLength = (existingContent, incomingContent) => {
    const maxOverlap = Math.min(existingContent.length, incomingContent.length);
    for (let size = maxOverlap; size > 0; size -= 1) {
        if (existingContent.slice(-size) === incomingContent.slice(0, size)) {
            return size;
        }
    }
    return 0;
};

const mergeAssistantContent = (existingContent, incomingContent) => {
    const current = typeof existingContent === 'string' ? existingContent : '';
    const incoming = typeof incomingContent === 'string' ? incomingContent : '';

    if (!incoming) return current;
    if (!current) return incoming;

    if (incoming.startsWith(current)) {
        return incoming;
    }

    if (current.startsWith(incoming)) {
        return current;
    }

    const overlapLength = computeOverlapLength(current, incoming);
    if (overlapLength > 0) {
        return `${current}${incoming.slice(overlapLength)}`;
    }

    return `${current}${incoming}`;
};

const buildClientContextMessages = (messages, currentQuestion) => {
    const safeMessages = Array.isArray(messages) ? messages : [];
    const normalized = safeMessages
        .filter((item) => item && (item.role === 'user' || item.role === 'assistant'))
        .map((item) => ({
            role: item.role,
            content: typeof item.content === 'string' ? item.content.trim() : '',
        }))
        .filter((item) => item.content.length > 0);

    const questionText = typeof currentQuestion === 'string' ? currentQuestion.trim() : '';
    if (questionText) {
        normalized.push({ role: 'user', content: questionText });
    }

    return normalized.slice(-30);
};

export const useAgentSocket = (endpoint, token, onConversationUpdate) => {
    const [messages, setMessages] = useState([]);
    const [conversationId, setConversationId] = useState(null);
    const onConversationUpdateRef = useRef(onConversationUpdate);
    const activeConversationIdRef = useRef(null);
    const activeRequestIdRef = useRef(null);

    // Construct WebSocket URL
    const wsBase = getWsBase();
    const wsUrl = wsBase && endpoint ? buildWebSocketUrlSafe(wsBase, endpoint, token) : null;

    // Use the robust connection hook
    const eventNamespace = endpoint || 'default';
    const { state: status, sendMessage: sendSocketMessage } = useRealtimeConnection(wsUrl, token, eventNamespace);

    useEffect(() => {
        onConversationUpdateRef.current = onConversationUpdate;
    }, [onConversationUpdate]);

    useEffect(() => {
        activeConversationIdRef.current = conversationId;
    }, [conversationId]);

    const refreshConversationHistory = useCallback(() => {
        if (!onConversationUpdateRef.current) return;
        onConversationUpdateRef.current();
    }, []);

    const addMessage = useCallback((msg) => {
        setMessages(prev => [...prev, msg]);
    }, []);

    const isStreamLifecycleEvent = (eventType) => {
        return (
            eventType === 'delta' ||
            eventType === 'assistant_delta' ||
            eventType === 'assistant_final' ||
            eventType === 'assistant_fallback' ||
            eventType === 'persisted' ||
            eventType === 'complete' ||
            eventType === 'error' ||
            eventType === 'assistant_error'
        );
    };

    // Handle incoming events (decoupled from socket logic)
    useEffect(() => {
        const handler = (e) => {
            const { type, payload } = e.detail || {};
            const incomingConversationId = payload?.conversation_id;
            const incomingRequestId = payload?.request_id;
            const activeConversationId = activeConversationIdRef.current;
            const activeRequestId = activeRequestIdRef.current;
            const hasActiveConversation = activeConversationId !== null && activeConversationId !== undefined;
            const hasIncomingConversation = incomingConversationId !== null && incomingConversationId !== undefined;
            if (hasActiveConversation && hasIncomingConversation) {
                const normalizedActive = Number.parseInt(String(activeConversationId), 10);
                const normalizedIncoming = Number.parseInt(String(incomingConversationId), 10);
                if (
                    !Number.isNaN(normalizedActive) &&
                    !Number.isNaN(normalizedIncoming) &&
                    normalizedActive !== normalizedIncoming
                ) {
                    return;
                }
            }
            // Accept events without request_id for backward compatibility with older gateways.
            // Reject only when both sides have explicit IDs and they mismatch.
            if (
                activeRequestId &&
                incomingRequestId &&
                String(activeRequestId) !== String(incomingRequestId)
            ) {
                return;
            }
            // Defensive gate: if no active request, ignore stray stream events from
            // other conversations/tabs unless they explicitly initialize a conversation.
            if (!activeRequestId && type !== 'conversation_init' && isStreamLifecycleEvent(type)) {
                return;
            }

            if (type === 'conversation_init') {
                if (payload?.conversation_id) {
                    setConversationId(payload.conversation_id);
                }
                refreshConversationHistory();
            } else if (type === 'delta' || type === 'assistant_delta') {
                const content = payload?.content || '';
                if (!content) return;
                const nestedAssistantError = parseNestedAssistantError(content);
                if (nestedAssistantError) {
                    notifyAgentError(nestedAssistantError);
                    return;
                }

                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant' && !last.isComplete && !last.isError) {
                        const updated = {
                            ...last,
                            content: mergeAssistantContent(last.content, content),
                        };
                        return [...prev.slice(0, -1), updated];
                    } else {
                         return [...prev, { id: generateId(), role: 'assistant', content: content, isComplete: false }];
                    }
                });
            } else if (type === 'complete') {
                 activeRequestIdRef.current = null;
                 setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                        return [...prev.slice(0, -1), { ...last, isComplete: true }];
                    }
                    return prev;
                });
            } else if (type === 'assistant_final') {
                const content = payload?.content || '';
                const nestedAssistantError = parseNestedAssistantError(content);
                if (nestedAssistantError) {
                    notifyAgentError(nestedAssistantError);
                    return;
                }
                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant' && !last.isComplete && !last.isError) {
                         const newContent = mergeAssistantContent(last.content, content);
                         return [...prev.slice(0, -1), { ...last, content: newContent, isComplete: true }];
                    } else if (content) {
                         return [...prev, { id: generateId(), role: 'assistant', content: content, isComplete: true }];
                    }
                    return prev;
                });
            } else if (type === 'persisted') {
                refreshConversationHistory();
            } else if (type === 'assistant_fallback') {
                 const content = payload?.content || '';
                 const nestedAssistantError = parseNestedAssistantError(content);
                 if (nestedAssistantError) {
                    notifyAgentError(nestedAssistantError);
                    return;
                 }
                 if (content) {
                    addMessage({ id: generateId(), role: 'assistant', content: content, isComplete: true });
                 }
                 refreshConversationHistory();
            } else if (type === 'error') {
                activeRequestIdRef.current = null;
                const details = payload?.details || 'Unknown error';
                notifyAgentError(String(details));
                refreshConversationHistory();
            } else if (type === 'assistant_error') {
                activeRequestIdRef.current = null;
                const content = payload?.content || 'Unknown assistant error';
                notifyAgentError(String(content));
                refreshConversationHistory();
            }
        };

        const eventName = `agent:event:${eventNamespace}`;
        window.addEventListener(eventName, handler);
        return () => window.removeEventListener(eventName, handler);
    }, [addMessage, refreshConversationHistory, eventNamespace]);

    const sendMessage = useCallback((text, metadata = {}) => {
        if (!text.trim()) return;

        // Optimistic UI update
        addMessage({ id: generateId(), role: 'user', content: text });

        const clientRequestId = generateId();
        activeRequestIdRef.current = clientRequestId;

        const payload = {
            question: text,
            client_request_id: clientRequestId,
            client_context_messages: buildClientContextMessages(messages, text),
            ...metadata,
        };
        if (conversationId !== null && conversationId !== undefined) {
            const normalizedConversationId = Number.parseInt(String(conversationId), 10);
            payload.conversation_id = Number.isNaN(normalizedConversationId)
                ? conversationId
                : normalizedConversationId;
        }

        // Send via robust connection
        sendSocketMessage(payload);

    }, [conversationId, addMessage, sendSocketMessage, messages]);

    const clearMessages = () => {
        activeRequestIdRef.current = null;
        setMessages([]);
    };
    const setMessagesSafe = (msgs) => setMessages(msgs);

    return {
        messages,
        sendMessage,
        status, // 'idle' | 'connecting' | 'connected' | 'degraded' | 'offline'
        conversationId,
        setConversationId,
        clearMessages,
        setMessages: setMessagesSafe,
        agentStates: {} // Deprecated
    };
};
