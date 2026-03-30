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

export const useAgentSocket = (endpoint, token, onConversationUpdate) => {
    const [messages, setMessages] = useState([]);
    const [conversationId, setConversationId] = useState(null);
    const onConversationUpdateRef = useRef(onConversationUpdate);

    // Construct WebSocket URL
    const wsBase = getWsBase();
    const wsUrl = wsBase && endpoint ? buildWebSocketUrlSafe(wsBase, endpoint, token) : null;

    // Use the robust connection hook
    const { state: status, sendMessage: sendSocketMessage } = useRealtimeConnection(wsUrl, token);

    useEffect(() => {
        onConversationUpdateRef.current = onConversationUpdate;
    }, [onConversationUpdate]);

    const refreshConversationHistory = useCallback(() => {
        if (!onConversationUpdateRef.current) return;
        onConversationUpdateRef.current();
    }, []);

    const addMessage = useCallback((msg) => {
        setMessages(prev => [...prev, msg]);
    }, []);

    // Handle incoming events (decoupled from socket logic)
    useEffect(() => {
        const handler = (e) => {
            const { type, payload } = e.detail || {};

            if (type === 'conversation_init') {
                if (payload?.conversation_id) {
                    setConversationId(payload.conversation_id);
                }
                refreshConversationHistory();
            } else if (type === 'delta' || type === 'assistant_delta') {
                const content = payload?.content || '';
                if (!content) return;

                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant' && !last.isComplete && !last.isError) {
                        const updated = { ...last, content: last.content + content };
                        return [...prev.slice(0, -1), updated];
                    } else {
                         return [...prev, { id: generateId(), role: 'assistant', content: content, isComplete: false }];
                    }
                });
            } else if (type === 'complete') {
                 setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant') {
                        return [...prev.slice(0, -1), { ...last, isComplete: true }];
                    }
                    return prev;
                });
            } else if (type === 'assistant_final') {
                const content = payload?.content || '';
                setMessages(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.role === 'assistant' && !last.isComplete && !last.isError) {
                         const newContent = last.content + content;
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
                 if (content) {
                    addMessage({ id: generateId(), role: 'assistant', content: content, isComplete: true });
                 }
                 refreshConversationHistory();
            } else if (type === 'error') {
                const details = payload?.details || 'Unknown error';
                addMessage({ id: generateId(), role: 'assistant', content: `Error: ${details}`, isError: true });
                refreshConversationHistory();
            } else if (type === 'assistant_error') {
                const content = payload?.content || 'Unknown assistant error';
                addMessage({ id: generateId(), role: 'assistant', content: `Error: ${content}`, isError: true });
                refreshConversationHistory();
            }
        };

        window.addEventListener('agent:event', handler);
        return () => window.removeEventListener('agent:event', handler);
    }, [addMessage, refreshConversationHistory]);

    const sendMessage = useCallback((text, metadata = {}) => {
        if (!text.trim()) return;

        // Optimistic UI update
        addMessage({ id: generateId(), role: 'user', content: text });

        const payload = { question: text, ...metadata };
        if (conversationId) payload.conversation_id = String(conversationId);

        // Send via robust connection
        sendSocketMessage(payload);

    }, [conversationId, addMessage, sendSocketMessage]);

    const clearMessages = () => setMessages([]);
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
