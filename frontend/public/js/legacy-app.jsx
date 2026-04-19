const { useState, useEffect, useRef, useCallback, memo } = React;

        // ══════════════════════════════════════════════════════════════════════
        // GLOBAL ERROR HANDLING | معالجة الأخطاء العالمية
        // ══════════════════════════════════════════════════════════════════════
        
        // Catch unhandled promise rejections (critical for Codespaces stability)
        window.addEventListener('unhandledrejection', (event) => {
            console.error('Unhandled promise rejection:', event.reason);
            event.preventDefault(); // Prevent browser crash
        });

        // Catch general errors
        window.addEventListener('error', (event) => {
            console.error('Global error caught:', event.error);
            event.preventDefault(); // Prevent browser crash
        });

        // CRITICAL FIX: Memory monitoring moved to component level to enable proper cleanup
        // Previously these global setInterval calls caused memory leaks and browser crashes
        // Now they will be managed inside the App component with proper cleanup on unmount

        // ══════════════════════════════════════════════════════════════════════
        // PERFORMANCE CONFIGURATION | تكوين الأداء
        // ══════════════════════════════════════════════════════════════════════
        
        // CRITICAL: Detect Codespaces environment for resource optimization
        const IS_CODESPACES = window.location.hostname.includes('github.dev') || 
                             window.location.hostname.includes('app.github.dev') ||
                             window.location.hostname.includes('preview.app.github.dev');
        
        const IS_CLOUD_ENV = IS_CODESPACES || 
                            window.location.hostname.includes('gitpod.io') ||
                            window.location.hostname.includes('repl.it');
        
        console.log(`🌍 Environment: ${IS_CODESPACES ? 'GitHub Codespaces' : IS_CLOUD_ENV ? 'Cloud IDE' : 'Local/Production'}`);
        
        // Showdown converter with performance optimizations
        const showdownConverter = new showdown.Converter({
            simplifiedAutoLink: true,
            excludeTrailingPunctuationFromURLs: true,
            strikethrough: true,
            tables: true,
            tasklists: true,
            simpleLineBreaks: true,
            openLinksInNewWindow: true
        });
        
        // DOM SAFETY VALVE: Limit messages to prevent memory exhaustion
        // More aggressive limits in cloud environments
        const MAX_MESSAGES = IS_CLOUD_ENV ? 10 : 15;
        
        // CODESPACES COMPATIBILITY: Reduced limits for cloud environments
        const MAX_STREAM_CHUNK_SIZE = IS_CLOUD_ENV ? 800 : 1000;
        const STREAM_UPDATE_THROTTLE = IS_CLOUD_ENV ? 400 : 300; // Higher throttle for Codespaces
        const STREAM_MICRO_DELAY = IS_CLOUD_ENV ? 12 : 8; // Longer delays in cloud
        
        console.log(`⚙️ Performance Config: MAX_MESSAGES=${MAX_MESSAGES}, THROTTLE=${STREAM_UPDATE_THROTTLE}ms, DELAY=${STREAM_MICRO_DELAY}ms`);
        
        // Performance monitoring
        const PERFORMANCE_MONITOR = {
            renderCount: 0,
            lastRenderTime: 0,
            avgRenderTime: 0
        };


        const API_ORIGIN = (() => {
            const protocol = window.location.protocol;
            const hostname = window.location.hostname;
            const port = window.location.port;
            if (port === '3000') {
                return `${protocol}//${hostname}:8000`;
            }
            return window.location.origin;
        })();

        const apiUrl = (path) => `${API_ORIGIN}${path}`;
        const wsBase = API_ORIGIN.replace(/^http/, 'ws');

        // Error Boundary to prevent "Browser Explosion"
        class ErrorBoundary extends React.Component {
            constructor(props) {
                super(props);
                this.state = { hasError: false };
            }

            static getDerivedStateFromError(error) {
                return { hasError: true };
            }

            componentDidCatch(error, errorInfo) {
                console.error("React Error Boundary caught an error:", error, errorInfo);
            }

            render() {
                if (this.state.hasError) {
                    return (
                        <div style={{ padding: '20px', color: 'var(--error-color)', textAlign: 'center' }}>
                            <h2>⚠️ Interface Error</h2>
                            <p>Something went wrong rendering the chat interface.</p>
                            <button onClick={() => window.location.reload()} style={{ width: 'auto', marginTop: '10px' }}>
                                Reload Application
                            </button>
                        </div>
                    );
                }
                return this.props.children;
            }
        }

        // ══════════════════════════════════════════════════════════════════════
        // MEMOIZED MARKDOWN COMPONENT | مكون Markdown المحسّن
        // ══════════════════════════════════════════════════════════════════════
        // CRITICAL: Prevents re-parsing markdown for unchanged messages
        // This is a key performance optimization following React best practices
        
        const Markdown = memo(({ content }) => {
            const startTime = performance.now();
            
            // SAFEGUARD: Truncate content to prevent Showdown regex freeze
            const MAX_CONTENT_LENGTH = 20000;  // Optimized for Codespaces
            const safeContent = (content || "").length > MAX_CONTENT_LENGTH
                ? (content.substring(0, MAX_CONTENT_LENGTH) + "\n\n... [Message Truncated] ...")
                : (content || "");

            // Parse markdown with error handling
            let html;
            try {
                html = showdownConverter.makeHtml(safeContent);
            } catch (error) {
                console.error("Markdown parsing error:", error);
                html = `<pre>${safeContent}</pre>`;
            }
            
            // Performance tracking
            const renderTime = performance.now() - startTime;
            PERFORMANCE_MONITOR.renderCount++;
            PERFORMANCE_MONITOR.lastRenderTime = renderTime;
            PERFORMANCE_MONITOR.avgRenderTime = 
                (PERFORMANCE_MONITOR.avgRenderTime * (PERFORMANCE_MONITOR.renderCount - 1) + renderTime) 
                / PERFORMANCE_MONITOR.renderCount;
            
            if (renderTime > 100) {
                console.warn(`Slow markdown render: ${renderTime.toFixed(2)}ms`);
            }
            
            return <div className="markdown-content" dangerouslySetInnerHTML={{ __html: html }} />;
        }, (prevProps, nextProps) => {
            // Strict equality check for memoization
            return prevProps.content === nextProps.content;
        });

        // Helper to generate unique IDs
        const generateId = () => Math.random().toString(36).substr(2, 9) + Date.now().toString(36);

        const buildClientContextMessages = (messages, currentQuestion, maxItems = 30) => {
            const safeMessages = Array.isArray(messages) ? messages : [];
            const normalizedHistory = safeMessages
                .filter(
                    (item) =>
                        item &&
                        (item.role === 'user' || item.role === 'assistant') &&
                        typeof item.content === 'string' &&
                        item.content.trim().length > 0
                )
                .map((item) => ({
                    role: item.role,
                    content: item.content.trim(),
                }));

            const questionText = typeof currentQuestion === 'string' ? currentQuestion.trim() : '';
            if (questionText.length > 0) {
                normalizedHistory.push({ role: 'user', content: questionText });
            }

            return normalizedHistory.slice(-maxItems);
        };

        const App = () => {
            const [token, setToken] = useState(localStorage.getItem('token'));
            const [user, setUser] = useState(null);
            const [isLoading, setIsLoading] = useState(!!localStorage.getItem('token'));

            useEffect(() => {
                const fetchUser = async () => {
                    if (token) {
                        try {
                            const response = await fetch(apiUrl('/api/security/user/me'), {
                                headers: { 'Authorization': `Bearer ${token}` }
                            });
                            if (response.ok) {
                                const userData = await response.json();
                                setUser(userData);
                            } else {
                                logout();
                            }
                        } catch (error) {
                            console.error("Failed to fetch user:", error);
                            logout();
                        } finally {
                            setIsLoading(false);
                        }
                    } else {
                        setIsLoading(false);
                    }
                };
                fetchUser();
            }, [token]);

            // CRITICAL FIX: Memory monitoring and GC with proper cleanup
            // This prevents memory leaks that were causing browser crashes in Codespaces
            useEffect(() => {
                const timers = [];
                
                // Memory monitoring (Codespaces has limited resources)
                if (performance.memory) {
                    const memoryTimer = setInterval(() => {
                        const usedMemory = performance.memory.usedJSHeapSize;
                        const totalMemory = performance.memory.jsHeapSizeLimit;
                        const percentUsed = (usedMemory / totalMemory) * 100;
                        
                        if (percentUsed > 90) {
                            console.warn(`⚠️ High memory usage: ${percentUsed.toFixed(1)}%`);
                        }
                        
                        // CRITICAL: Auto-reload if memory exceeds 95% in Codespaces
                        if (IS_CODESPACES && percentUsed > 95) {
                            console.error('🚨 CRITICAL: Memory exhaustion detected! Forcing reload to prevent crash...');
                            setTimeout(() => {
                                window.location.reload();
                            }, 2000);
                        }
                    }, 30000); // Check every 30 seconds
                    timers.push(memoryTimer);
                }

                // Periodic garbage collection hint for memory optimization
                const gcTimer = setInterval(() => {
                    if (window.gc) {
                        window.gc(); // Manual GC if available (Chrome with --expose-gc flag)
                    }
                }, 60000); // Every 60 seconds
                timers.push(gcTimer);
                
                // CODESPACES: Health check to detect server issues
                if (IS_CODESPACES) {
                    let consecutiveFailures = 0;
                    const healthTimer = setInterval(async () => {
                        try {
                            // Create manual timeout with AbortController for better browser compatibility
                            const controller = new AbortController();
                            const timeoutId = setTimeout(() => controller.abort(), 5000);
                            
                            const response = await fetch(apiUrl('/health'), { 
                                method: 'GET',
                                cache: 'no-cache',
                                signal: controller.signal
                            });
                            
                            clearTimeout(timeoutId);
                            
                            if (response.ok) {
                                consecutiveFailures = 0;
                            } else {
                                consecutiveFailures++;
                                console.warn(`⚠️ Health check failed (${consecutiveFailures}/3)`);
                            }
                        } catch (error) {
                            consecutiveFailures++;
                            console.warn(`⚠️ Health check error (${consecutiveFailures}/3):`, error.message);
                        }
                        
                        // If 3 consecutive failures, show warning
                        if (consecutiveFailures >= 3) {
                            console.error('🚨 Server appears to be down. Page will reload in 5 seconds...');
                            setTimeout(() => {
                                window.location.reload();
                            }, 5000);
                            clearInterval(healthTimer);
                        }
                    }, 60000); // Check every 60 seconds
                    timers.push(healthTimer);
                }

                // CLEANUP: Clear all timers when component unmounts
                return () => {
                    timers.forEach(timer => clearInterval(timer));
                };
            }, []); // Empty dependency array - run once on mount

            const handleLogin = (newToken, userData) => {
                localStorage.setItem('token', newToken);
                setToken(newToken);
                setUser(userData);
                // Don't manipulate browser history - let React handle rendering
                // The issue with pushState in Codespaces was causing browser crashes
            };

            const logout = () => {
                try {
                    localStorage.removeItem('token');
                    setToken(null);
                    setUser(null);
                    // Use replace instead of href to prevent browser history issues
                    window.location.replace('/');
                } catch (error) {
                    console.error('Logout error:', error);
                    // Force reload as fallback
                    window.location.reload();
                }
            };

            if (isLoading) {
                return (
                    <div className="loading-screen">
                        <i className="fas fa-circle-notch fa-spin"></i>
                        <h2>Initializing Reality Kernel...</h2>
                    </div>
                );
            }

            if (!token || !user) {
                return <AuthScreen onLogin={handleLogin} />;
            }

            if (user.is_admin) {
               return <AdminDashboard user={user} onLogout={logout} />;
            } else {
               return <CustomerDashboard user={user} onLogout={logout} />;
            }
        };

        const AuthScreen = ({ onLogin }) => {
            const [isLogin, setIsLogin] = useState(true);
            return (
                <div className="login-container">
                    {isLogin ?
                        <LoginForm onLogin={onLogin} onToggle={() => setIsLogin(false)} /> :
                        <RegisterForm onToggle={() => setIsLogin(true)} />
                    }
                </div>
            );
        };

        const LoginForm = ({ onLogin, onToggle }) => {
            const [email, setEmail] = useState('');
            const [password, setPassword] = useState('');
            const [error, setError] = useState('');
            const [isSubmitting, setIsSubmitting] = useState(false);

            const handleSubmit = async (e) => {
                e.preventDefault();
                setError('');
                setIsSubmitting(true);
                try {
                    const response = await fetch(apiUrl('/api/security/login'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, password })
                    });
                    if (response.ok) {
                        const data = await response.json();
                        onLogin(data.access_token, data.user);
                    } else {
                        const errorData = await response.json();
                        setError(errorData.detail || 'Login failed');
                    }
                } catch (err) {
                    setError('An error occurred. Please try again.');
                } finally {
                    setIsSubmitting(false);
                }
            };

            return (
                <div className="login-form">
                    <form onSubmit={handleSubmit}>
                        <h2>Login</h2>
                        <div className="error-message">{error}</div>
                        <div className="input-group">
                            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" required />
                        </div>
                        <div className="input-group">
                            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" required />
                        </div>
                        <button type="submit" disabled={isSubmitting}>
                            {isSubmitting ? <i className="fas fa-spinner fa-spin"></i> : 'Login'}
                        </button>
                    </form>
                    <div className="toggle-form">
                        <a onClick={onToggle}>Don't have an account? Register</a>
                    </div>
                </div>
            );
        };

        const RegisterForm = ({ onToggle }) => {
            const [name, setName] = useState('');
            const [email, setEmail] = useState('');
            const [password, setPassword] = useState('');
            const [error, setError] = useState('');
            const [success, setSuccess] = useState('');
            const [isSubmitting, setIsSubmitting] = useState(false);

            const handleSubmit = async (e) => {
                e.preventDefault();
                setError('');
                setSuccess('');
                setIsSubmitting(true);
                try {
                    const response = await fetch(apiUrl('/api/security/register'), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ full_name: name, email, password, is_admin: false })
                    });
                    if (response.ok) {
                        setSuccess('Registration successful! Please login.');
                        setTimeout(onToggle, 2000);
                    } else {
                        const errorData = await response.json();
                        setError(errorData.detail || 'Registration failed');
                    }
                } catch (err) {
                    setError('An error occurred. Please try again.');
                } finally {
                    setIsSubmitting(false);
                }
            };

            return (
                <div className="register-form">
                    <form onSubmit={handleSubmit}>
                         <h2>Register</h2>
                        <div className="error-message">{error}</div>
                        {success && <div style={{color: 'lightgreen', textAlign: 'center', marginBottom: '15px'}}>{success}</div>}
                        <div className="input-group">
                             <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="Name" required />
                        </div>
                        <div className="input-group">
                            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Email" required />
                        </div>
                        <div className="input-group">
                             <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Password" required />
                        </div>
                        <button type="submit" disabled={isSubmitting}>
                             {isSubmitting ? <i className="fas fa-spinner fa-spin"></i> : 'Register'}
                        </button>
                    </form>
                    <div className="toggle-form">
                        <a onClick={onToggle}>Already have an account? Login</a>
                    </div>
                </div>
            );
        };

        const CustomerDashboard = ({ user, onLogout }) => {
            const [messages, setMessages] = useState([]);
            const [conversationId, setConversationId] = useState(null);
            const [conversations, setConversations] = useState([]);
            const [input, setInput] = useState('');
            const [isLoadingConversation, setIsLoadingConversation] = useState(false);
            const messagesEndRef = useRef(null);
            const socketRef = useRef(null);

            useEffect(() => {
                return () => {
                    if (socketRef.current) {
                        socketRef.current.close();
                    }
                };
            }, []);

            const scrollToBottom = () => {
                if (messagesEndRef.current) {
                    requestAnimationFrame(() => {
                        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
                    });
                }
            };

            const messagesLength = messages.length;
            useEffect(() => {
                scrollToBottom();
            }, [messagesLength]);

            const normalizeMessages = (msgs) => {
                return msgs.map(msg => ({
                    ...msg,
                    id: msg.id || generateId()
                }));
            };

            const safeSetMessages = useCallback((update) => {
                setMessages(prev => {
                    let nextMessages;
                    if (typeof update === 'function') {
                        nextMessages = update(prev);
                    } else {
                        nextMessages = Array.isArray(update) ? normalizeMessages(update) : update;
                    }
                    if (nextMessages.length > MAX_MESSAGES) {
                        return nextMessages.slice(nextMessages.length - MAX_MESSAGES);
                    }
                    return nextMessages;
                });
            }, []);

            useEffect(() => {
                const fetchLatest = async () => {
                    try {
                        const token = localStorage.getItem('token');
                        const res = await fetch(apiUrl('/api/chat/latest'), {
                            headers: { 'Authorization': `Bearer ${token}` }
                        });
                        if (res.ok) {
                            const data = await res.json();
                            if (data?.messages && Array.isArray(data.messages)) {
                                safeSetMessages(data.messages);
                            }
                            if (data?.conversation_id) {
                                setConversationId(data.conversation_id);
                            }
                        }
                    } catch (e) {
                        console.error("Failed to fetch latest chat", e);
                    }
                };
                const fetchConversations = async () => {
                    try {
                        const token = localStorage.getItem('token');
                        const res = await fetch(apiUrl('/api/chat/conversations'), {
                            headers: { 'Authorization': `Bearer ${token}` }
                        });
                        if (res.ok) {
                            const data = await res.json();
                            setConversations(data);
                        }
                    } catch (e) {
                        console.error("Failed to fetch conversations", e);
                    }
                };
                fetchConversations();
                fetchLatest();
            }, []);

            const loadConversation = async (id) => {
                if (!id) return;
                setConversationId(id);
                setIsLoadingConversation(true);
                setMessages([]);
                try {
                    const token = localStorage.getItem('token');
                    const res = await fetch(apiUrl(`/api/chat/conversations/${id}`), {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        safeSetMessages(data.messages || []);
                        setConversationId(data.conversation_id);
                    } else {
                        const errorData = await res.json().catch(() => ({}));
                        const errorMessage = errorData.detail || 'Failed to load conversation';
                        safeSetMessages([{ id: generateId(), role: 'assistant', content: `Error: ${errorMessage}` }]);
                    }
                } catch (e) {
                    console.error("Failed to load conversation", e);
                    safeSetMessages([{ id: generateId(), role: 'assistant', content: 'Error: Failed to load conversation. Please try again.' }]);
                } finally {
                    setIsLoadingConversation(false);
                }
            };

            const handleNewChat = () => {
                setMessages([]);
                setConversationId(null);
            };

            const handleSend = async () => {
                if (!input.trim()) return;

                if (socketRef.current) {
                    socketRef.current.close();
                }

                const userMsgId = generateId();
                const question = input;
                safeSetMessages(prev => [...prev, { id: userMsgId, role: 'user', content: question }]);
                setInput('');

                const token = localStorage.getItem('token');
                if (!token) {
                    safeSetMessages(prev => [...prev, { id: generateId(), role: 'assistant', content: 'Error: Missing auth token.' }]);
                    return;
                }

                const clientContextMessages = buildClientContextMessages(messages, question);

                const payload = {
                    question,
                    client_context_messages: clientContextMessages,
                };
                if (conversationId !== null && conversationId !== undefined) {
                    const normalizedConversationId = Number.parseInt(String(conversationId), 10);
                    payload.conversation_id = Number.isNaN(normalizedConversationId)
                        ? conversationId
                        : normalizedConversationId;
                }

                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                const wsUrl = `${wsBase}/api/chat/ws`;
                const socket = new WebSocket(wsUrl, ['jwt', token]);
                socketRef.current = socket;

                let assistantMessage = '';
                let isNewMessage = true;
                let lastUpdateTimestamp = 0;
                const assistantMsgId = generateId();

                socket.onopen = () => {
                    socket.send(JSON.stringify(payload));
                };

                socket.onmessage = async (event) => {
                    try {
                        const parsed = JSON.parse(event.data);
                        if (parsed.type === 'status') {
                            return;
                        }
                        if (parsed.type === 'conversation_init') {
                            const initPayload = parsed.payload || {};
                            if (initPayload.conversation_id) {
                                setConversationId(initPayload.conversation_id);
                            }
                            isNewMessage = true;
                            const refreshToken = localStorage.getItem('token');
                            fetch(apiUrl('/api/chat/conversations'), {
                                headers: { 'Authorization': `Bearer ${refreshToken}` }
                            }).then(res => res.ok ? res.json() : [])
                              .then(data => setConversations(Array.isArray(data) ? data : []))
                              .catch(() => {});
                            return;
                        }

                        if (parsed.type === 'delta') {
                            const content = parsed?.payload?.content || '';
                            if (!content) return;

                            if (isNewMessage) {
                                assistantMessage = content;
                                safeSetMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: assistantMessage }]);
                                isNewMessage = false;
                                lastUpdateTimestamp = Date.now();
                            } else {
                                if (assistantMessage.length < 50000) {
                                    assistantMessage += content;
                                }

                                const now = Date.now();
                                if (now - lastUpdateTimestamp > STREAM_UPDATE_THROTTLE) {
                                    safeSetMessages(prev =>
                                        prev.map(msg =>
                                            msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                                        )
                                    );
                                    lastUpdateTimestamp = now;
                                }
                            }
                            return;
                        }

                        if (parsed.type === 'complete') {
                            if (!isNewMessage) {
                                safeSetMessages(prev =>
                                    prev.map(msg =>
                                        msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                                    )
                                );
                            }
                            socket.close();
                            return;
                        }

                        if (parsed.type === 'error') {
                            const details = parsed?.payload?.details || 'Unexpected error.';
                            safeSetMessages(prev => [...prev, { id: generateId(), role: 'assistant', content: `Error: ${details}` }]);
                        }
                    } catch (parseError) {
                        console.error('Parse error:', parseError);
                    }
                };

                socket.onerror = () => {
                    safeSetMessages(prev => [...prev, { id: generateId(), role: 'assistant', content: 'Sorry, I encountered a connection error.' }]);
                };

                socket.onclose = () => {
                    if (!isNewMessage) {
                        safeSetMessages(prev =>
                            prev.map(msg =>
                                msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                            )
                        );
                    }
                };
            };

            const handleKeyPress = (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                }
            };

            return (
                <div className="app-container">
                    <div className="header">
                        <h2>Overmind Education Chat - Welcome, {user.name}</h2>
                        <button onClick={onLogout} className="logout-btn"><i className="fas fa-sign-out-alt"></i> Logout</button>
                    </div>

                    <div className="dashboard-layout">
                        <div className="sidebar">
                             <div className="sidebar-header">
                                 <button className="new-chat-btn" onClick={handleNewChat}>
                                     <i className="fas fa-plus"></i> New Chat
                                 </button>
                             </div>
                             <div className="conversation-list">
                                 {conversations.map(conv => {
                                     const isActive = conversationId === conv.conversation_id;
                                     const iconClass = isLoadingConversation && isActive ? 'fa-spinner fa-spin' : 'fa-comment-alt';
                                     return (
                                         <div
                                             key={conv.conversation_id}
                                             className={`conversation-item ${isActive ? 'active' : ''}`}
                                             onClick={() => loadConversation(conv.conversation_id)}
                                         >
                                             <i className={`fas ${iconClass}`} style={{marginRight: '8px'}}></i>
                                             {conv.title || `Conversation ${conv.conversation_id}`}
                                         </div>
                                     );
                                 })}
                             </div>
                        </div>

                        <div className="chat-area">
                            <div className="chat-container">
                                <div className="messages">
                                    {isLoadingConversation ? (
                                        <div className="welcome-message">
                                            <i className="fas fa-spinner fa-spin" style={{fontSize: '2em', color: 'var(--primary-color)', marginBottom: '20px'}}></i>
                                            <p>Loading conversation...</p>
                                        </div>
                                    ) : messages.length === 0 ? (
                                        <div className="welcome-message">
                                            <i className="fas fa-graduation-cap" style={{fontSize: '3em', color: 'var(--primary-color)', marginBottom: '20px'}}></i>
                                            <h3 style={{margin: '10px 0', color: 'var(--primary-color)'}}>Education-Only Overmind</h3>
                                            <p style={{fontSize: '0.9em', color: '#666', marginBottom: '15px'}}>
                                                اسأل عن الرياضيات أو الفيزياء أو البرمجة أو الهندسة أو العلوم.
                                            </p>
                                            <p style={{marginTop: '15px', color: '#888'}}>ابدأ محادثة تعليمية الآن...</p>
                                        </div>
                                    ) : (
                                        messages.map((msg) => {
                                            const key = msg.id || Math.random();
                                            return (
                                                <div key={key} className={`message ${msg.role}`}>
                                                    <div className="message-bubble">
                                                        {msg.content}
                                                    </div>
                                                </div>
                                            );
                                        })
                                    )}
                                    <div ref={messagesEndRef} />
                                </div>
                                <div className="input-area">
                                    <textarea
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyPress={handleKeyPress}
                                        placeholder="اكتب سؤالك التعليمي هنا..."
                                        rows="3"
                                    />
                                    <button onClick={handleSend}>Send</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            );
        };

        const AdminDashboard = ({ user, onLogout }) => {
            const [messages, setMessages] = useState([]);
            const [conversations, setConversations] = useState([]);
            const [conversationId, setConversationId] = useState(null);
            const [input, setInput] = useState('');
            const [isLoadingConversation, setIsLoadingConversation] = useState(false);
            const messagesEndRef = useRef(null);
            const socketRef = useRef(null); // For managing WebSocket sessions

            // CRITICAL FIX: Cleanup on unmount to prevent memory leaks
            useEffect(() => {
                return () => {
                    if (socketRef.current) {
                        socketRef.current.close();
                    }
                };
            }, []);

            const scrollToBottom = () => {
                // Use requestAnimationFrame to avoid layout thrashing
                if (messagesEndRef.current) {
                    requestAnimationFrame(() => {
                        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
                    });
                }
            };

            // OPTIMIZED: Scroll only when messages array length changes, not on every update
            // This prevents excessive re-renders during streaming
            const messagesLength = messages.length;
            useEffect(() => {
                scrollToBottom();
            }, [messagesLength]);

            // Transform backend messages to include a stable ID
            const normalizeMessages = (msgs) => {
                return msgs.map(msg => ({
                    ...msg,
                    id: msg.id || generateId() // Ensure every message has a stable ID
                }));
            };

            // Helper to enforce safety valve with stable IDs
            const safeSetMessages = useCallback((update) => {
                setMessages(prev => {
                    let nextMessages;
                    if (typeof update === 'function') {
                        nextMessages = update(prev);
                    } else {
                        // Normalize incoming full updates
                        nextMessages = Array.isArray(update) ? normalizeMessages(update) : update;
                    }

                    // DOM SAFETY VALVE: Enforce strict limit
                    if (nextMessages.length > MAX_MESSAGES) {
                         return nextMessages.slice(nextMessages.length - MAX_MESSAGES);
                    }
                    return nextMessages;
                });
            }, []);

            const fetchConversations = async () => {
                try {
                    const token = localStorage.getItem('token');
                    const res = await fetch(apiUrl('/admin/api/conversations'), {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        setConversations(data);
                    }
                } catch (e) {
                    console.error("Failed to fetch conversations", e);
                }
            };

            const loadConversation = async (id) => {
                if (!id) return;
                setConversationId(id);
                setIsLoadingConversation(true);
                setMessages([]);
                try {
                    const token = localStorage.getItem('token');
                    const res = await fetch(apiUrl(`/admin/api/conversations/${id}`), {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (res.ok) {
                        const data = await res.json();
                        safeSetMessages(data.messages || []);
                        setConversationId(data.conversation_id);
                    } else {
                        const errorData = await res.json().catch(() => ({}));
                        const errorMessage = errorData.detail || 'Failed to load conversation';
                        safeSetMessages([{ id: generateId(), role: 'assistant', content: `Error: ${errorMessage}` }]);
                    }
                } catch (e) {
                    console.error("Failed to load conversation", e);
                    safeSetMessages([{ id: generateId(), role: 'assistant', content: 'Error: Failed to load conversation. Please try again.' }]);
                } finally {
                    setIsLoadingConversation(false);
                }
            };

            useEffect(() => {
                fetchConversations();
                const fetchLatest = async () => {
                     try {
                        const token = localStorage.getItem('token');
                        const res = await fetch(apiUrl('/admin/api/chat/latest'), {
                            headers: { 'Authorization': `Bearer ${token}` }
                        });
                        if (res.ok) {
                            const data = await res.json();
                            if (data.messages && Array.isArray(data.messages)) {
                                safeSetMessages(data.messages);
                            }
                            if (data.conversation_id) {
                                setConversationId(data.conversation_id);
                            }
                        }
                    } catch (e) {
                        console.error("Failed to fetch latest", e);
                    }
                };
                fetchLatest();
            }, []);

            const handleNewChat = () => {
                setMessages([]);
                setConversationId(null);
            };

            const handleSend = async () => {
                if (!input.trim()) return;

                if (socketRef.current) {
                    socketRef.current.close();
                }

                const userMsgId = generateId();
                const question = input;
                safeSetMessages(prev => [...prev, { id: userMsgId, role: 'user', content: input }]);
                setInput('');

                const token = localStorage.getItem('token');
                if (!token) {
                    safeSetMessages(prev => [...prev, { id: generateId(), role: 'assistant', content: 'Error: Missing auth token.' }]);
                    return;
                }

                const clientContextMessages = buildClientContextMessages(messages, question);

                const payload = {
                    question,
                    client_context_messages: clientContextMessages,
                };
                if (conversationId !== null && conversationId !== undefined) {
                    const normalizedConversationId = Number.parseInt(String(conversationId), 10);
                    payload.conversation_id = Number.isNaN(normalizedConversationId)
                        ? conversationId
                        : normalizedConversationId;
                }

                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                const wsUrl = `${wsBase}/admin/api/chat/ws`;
                const socket = new WebSocket(wsUrl, ['jwt', token]);
                socketRef.current = socket;

                let assistantMessage = '';
                let isNewMessage = true;
                let lastUpdateTimestamp = 0;
                const assistantMsgId = generateId();

                socket.onopen = () => {
                    socket.send(JSON.stringify(payload));
                };

                socket.onmessage = (event) => {
                    try {
                        const parsed = JSON.parse(event.data);
                        if (parsed.type === 'status') {
                            return;
                        }
                        if (parsed.type === 'conversation_init') {
                            const initPayload = parsed.payload || {};
                            if (initPayload.conversation_id) {
                                setConversationId(initPayload.conversation_id);
                            }
                            safeSetMessages(prev => [...prev, { id: generateId(), role: 'init', content: `Conversation ${initPayload.conversation_id} - ${initPayload.title || ''}` }]);
                            isNewMessage = true;
                            fetchConversations();
                            return;
                        }

                        if (parsed.type === 'delta') {
                            const content = parsed?.payload?.content || '';
                            if (!content) return;

                            if (isNewMessage) {
                                assistantMessage = content;
                                safeSetMessages(prev => [...prev, { id: assistantMsgId, role: 'assistant', content: assistantMessage }]);
                                isNewMessage = false;
                                lastUpdateTimestamp = Date.now();
                            } else {
                                if (assistantMessage.length < 50000) {
                                    assistantMessage += content;
                                } else if (!assistantMessage.endsWith("... [Truncated by Browser Safeguard]")) {
                                    assistantMessage += "\n\n... [Truncated by Browser Safeguard]";
                                    console.warn("Stream truncated to prevent browser crash (50k limit reached)");
                                }

                                const now = Date.now();
                                if (now - lastUpdateTimestamp > STREAM_UPDATE_THROTTLE) {
                                    safeSetMessages(prev =>
                                        prev.map(msg =>
                                            msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                                        )
                                    );
                                    lastUpdateTimestamp = now;
                                }
                            }
                            return;
                        }

                        if (parsed.type === 'complete') {
                            if (!isNewMessage) {
                                safeSetMessages(prev =>
                                    prev.map(msg =>
                                        msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                                    )
                                );
                            }
                            socket.close();
                            return;
                        }

                        if (parsed.type === 'error') {
                            const details = parsed?.payload?.details || 'Unexpected error.';
                            safeSetMessages(prev => [...prev, { id: generateId(), role: 'assistant', content: `Error: ${details}` }]);
                        }
                    } catch (e) {
                        console.error('Error parsing stream data:', e);
                    }
                };

                socket.onerror = () => {
                    safeSetMessages(prev => [
                        ...prev,
                        { id: generateId(), role: 'assistant', content: 'Sorry, I encountered a connection error.' }
                    ]);
                };

                socket.onclose = () => {
                    if (!isNewMessage) {
                        safeSetMessages(prev =>
                            prev.map(msg =>
                                msg.id === assistantMsgId ? { ...msg, content: assistantMessage } : msg
                            )
                        );
                    }
                };
            };

            const handleKeyPress = (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                }
            };

            return (
                <div className="app-container">
                    <div className="header">
                        <h2>Overmind CLI Mindgate - Welcome, {user.name}</h2>
                        <button onClick={onLogout} className="logout-btn"><i className="fas fa-sign-out-alt"></i> Logout</button>
                    </div>

                    <div className="dashboard-layout">
                        <div className="sidebar">
                             <div className="sidebar-header">
                                 <button className="new-chat-btn" onClick={handleNewChat}>
                                     <i className="fas fa-plus"></i> New Chat
                                 </button>
                             </div>
                             <div className="conversation-list">
                                 {conversations.map(conv => {
                                     const isActive = conversationId === conv.conversation_id;
                                     const isLoading = isActive && isLoadingConversation;
                                     const iconClass = isLoading ? 'fa-spinner fa-spin' : 'fa-comment-alt';
                                     return (
                                         <div
                                             key={conv.conversation_id}
                                             className={`conversation-item ${isActive ? 'active' : ''}`}
                                             onClick={() => loadConversation(conv.conversation_id)}
                                         >
                                             <i className={`fas ${iconClass}`} style={{marginRight: '8px'}}></i>
                                             {conv.title || `Conversation ${conv.conversation_id}`}
                                         </div>
                                     );
                                 })}
                             </div>
                        </div>

                        <div className="chat-area">
                            <div className="chat-container">
                                <div className="messages">
                                    {isLoadingConversation ? (
                                        <div className="welcome-message">
                                            <i className="fas fa-spinner fa-spin" style={{fontSize: '2em', color: 'var(--primary-color)', marginBottom: '20px'}}></i>
                                            <p>Loading conversation...</p>
                                        </div>
                                    ) : messages.length === 0 ? (
                                        <div className="welcome-message">
                                            <i className="fas fa-brain" style={{fontSize: '3em', color: 'var(--primary-color)', marginBottom: '20px'}}></i>
                                            <h3 style={{margin: '10px 0', color: 'var(--primary-color)'}}>🧠 OVERMIND CLI MINDGATE</h3>
                                            <p style={{fontSize: '0.9em', color: '#666', marginBottom: '15px'}}>
                                                <strong>الهوية:</strong> المُنسق الذكي الأعلى لمنصة CogniForge
                                            </p>
                                            <div style={{textAlign: 'right', fontSize: '0.85em', color: '#555', maxWidth: '500px', margin: '0 auto', padding: '15px', background: 'rgba(74, 144, 226, 0.05)', borderRadius: '10px', border: '1px solid rgba(74, 144, 226, 0.2)'}}>
                                                <p><strong>📊 القدرات:</strong></p>
                                                <ul style={{textAlign: 'right', paddingRight: '20px', margin: '10px 0'}}>
                                                    <li>تحليل المشاكل المعمارية المعقدة</li>
                                                    <li>اقتراح حلول كود جاهزة للتنفيذ</li>
                                                    <li>فهم سياق المحادثة السابقة</li>
                                                    <li>التواصل بالعربية والإنجليزية</li>
                                                </ul>
                                                <p style={{marginTop: '10px'}}><strong>🏗️ النظام:</strong> FastAPI + SQLAlchemy + Pydantic v2</p>
                                            </div>
                                            <p style={{marginTop: '15px', color: '#888'}}>ابدأ محادثة جديدة للتفاعل مع Overmind...</p>
                                        </div>
                                    ) : (
                                        messages.map((msg) => {
                                            // Ensure key is unique and stable. Fallback to random if no ID (should be covered by normalize)
                                            const key = msg.id || Math.random();
                                            if (msg.role === 'init') {
                                                return <div key={key} className="conversation-init">{msg.content}</div>;
                                            }
                                            return (
                                                <div key={key} className={`message ${msg.role}`}>
                                                    <div className="message-bubble">
                                                        <Markdown content={msg.content} />
                                                    </div>
                                                </div>
                                            );
                                        })
                                    )}
                                    <div ref={messagesEndRef} />
                                </div>
                                <div className="input-area">
                                    <textarea
                                        value={input}
                                        onChange={(e) => setInput(e.target.value)}
                                        onKeyPress={handleKeyPress}
                                        placeholder="Enter your command..."
                                        rows="1"
                                    />
                                    <button onClick={handleSend}><i className="fas fa-paper-plane"></i></button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            );
        };

        const rootElement = document.getElementById('root');

        if (!rootElement) {
            console.error('Legacy root element not found.');
            window.dispatchEvent(new CustomEvent('legacy-app-error', {
                detail: { message: 'تعذر العثور على عنصر تشغيل الواجهة.' }
            }));
        } else {
            ReactDOM.render(
                <ErrorBoundary>
                    <App />
                </ErrorBoundary>,
                rootElement,
                () => {
                    window.__legacyAppMounted = true;
                    window.dispatchEvent(new Event('legacy-app-mounted'));
                }
            );
        }
        
        // ══════════════════════════════════════════════════════════════════════
        // STARTUP DIAGNOSTICS | تشخيص بدء التشغيل
        // ══════════════════════════════════════════════════════════════════════
        console.log('╔══════════════════════════════════════════════════════════════════╗');
        console.log('║             CogniForge V3 - Startup Diagnostics                 ║');
        console.log('╚══════════════════════════════════════════════════════════════════╝');
        console.log(`🌍 Environment: ${IS_CODESPACES ? 'GitHub Codespaces' : IS_CLOUD_ENV ? 'Cloud IDE' : 'Local/Production'}`);
        console.log(`📊 Performance Limits:`);
        console.log(`   - MAX_MESSAGES: ${MAX_MESSAGES}`);
        console.log(`   - STREAM_UPDATE_THROTTLE: ${STREAM_UPDATE_THROTTLE}ms`);
        console.log(`   - STREAM_MICRO_DELAY: ${STREAM_MICRO_DELAY}ms`);
        console.log(`   - MAX_STREAM_CHUNK_SIZE: ${MAX_STREAM_CHUNK_SIZE} chars`);
        
        if (performance.memory) {
            const memoryMB = (performance.memory.jsHeapSizeLimit / 1024 / 1024).toFixed(0);
            console.log(`💾 Memory Limit: ${memoryMB} MB`);
        }
        
        console.log(`⚙️ React Version: ${React.version}`);
        console.log(`✅ Application initialized successfully`);
        console.log('═══════════════════════════════════════════════════════════════════');
        
        // Track initial load time
        window.addEventListener('load', () => {
            const loadTime = performance.now();
            console.log(`⏱️ Total load time: ${loadTime.toFixed(2)}ms`);
        });
