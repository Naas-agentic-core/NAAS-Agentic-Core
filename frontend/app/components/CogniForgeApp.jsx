"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { errorTracker } from '../utils/errorTracker';
import { useAgentSocket } from '../hooks/useAgentSocket';
import { ChatInterface } from './ChatInterface';
import { AgentTimeline } from './AgentTimeline';

const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? '';
const apiUrl = (path) => `${API_ORIGIN}${path}`;

class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }
    static getDerivedStateFromError(error) { return { hasError: true }; }
    componentDidCatch(error, errorInfo) { errorTracker.reportError(error, { errorInfo, source: "React ErrorBoundary" }); }
    render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: '20px', color: 'var(--error-color)', textAlign: 'center' }}>
                    <h2>⚠️ Interface Error</h2>
                    <button onClick={() => window.location.reload()} style={{ padding: '10px 20px', marginTop: '10px', cursor: 'pointer' }}>إعادة تحميل</button>
                </div>
            );
        }
        return this.props.children;
    }
}

const LoginForm = ({ onLogin, onToggle }) => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await fetch(apiUrl('/api/security/login'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            if (res.ok) {
                const data = await res.json();
                onLogin(data.access_token, data.user);
            } else {
                setError((await res.json()).detail || 'Login failed');
            }
        } catch (e) { setError('Connection failed'); }
        finally { setLoading(false); }
    };

    return (
        <div className="login-form">
            <form onSubmit={handleSubmit}>
                <h2>تسجيل الدخول</h2>
                {error && <div className="error-message">{error}</div>}
                <div className="input-group"><input type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="البريد الإلكتروني" required /></div>
                <div className="input-group"><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="كلمة المرور" required /></div>
                <button disabled={loading} style={{width: '100%', padding: '0.75rem', backgroundColor: 'var(--primary-color)', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer'}}>{loading ? '...' : 'دخول'}</button>
            </form>
            <div className="toggle-form"><a onClick={onToggle}>إنشاء حساب جديد</a></div>
        </div>
    );
};

const RegisterForm = ({ onToggle }) => {
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            const res = await fetch(apiUrl('/api/security/register'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name: name, email, password })
            });
            if (res.ok) {
                alert('Registration successful');
                onToggle();
            } else {
                setError((await res.json()).detail || 'Failed');
            }
        } catch (e) { setError('Error'); }
        finally { setLoading(false); }
    };

    return (
        <div className="register-form">
            <form onSubmit={handleSubmit}>
                <h2>إنشاء حساب</h2>
                {error && <div className="error-message">{error}</div>}
                <div className="input-group"><input value={name} onChange={e=>setName(e.target.value)} placeholder="الاسم الكامل" required /></div>
                <div className="input-group"><input value={email} onChange={e=>setEmail(e.target.value)} placeholder="البريد الإلكتروني" required /></div>
                <div className="input-group"><input type="password" value={password} onChange={e=>setPassword(e.target.value)} placeholder="كلمة المرور" required /></div>
                <button disabled={loading} style={{width: '100%', padding: '0.75rem', backgroundColor: 'var(--primary-color)', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer'}}>{loading ? '...' : 'تسجيل'}</button>
            </form>
            <div className="toggle-form"><a onClick={onToggle}>لديك حساب بالفعل؟ تسجيل الدخول</a></div>
        </div>
    );
};

const AuthScreen = ({ onLogin }) => {
    const [isLogin, setIsLogin] = useState(true);
    return (
        <div className="login-container">
            {isLogin ? <LoginForm onLogin={onLogin} onToggle={() => setIsLogin(false)} /> : <RegisterForm onToggle={() => setIsLogin(true)} />}
        </div>
    );
};

const DashboardLayout = ({ user, onLogout }) => {
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);
    const [isAgentSidebarOpen, setIsAgentSidebarOpen] = useState(false);
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [theme, setTheme] = useState('dark');
    const [conversations, setConversations] = useState([]);
    const menuRef = useRef(null);

    const endpoint = user.is_admin ? '/admin/api/chat/ws' : '/api/chat/ws';
    const convEndpoint = user.is_admin ? '/admin/api/conversations' : '/api/chat/conversations';
    const historyEndpoint = user.is_admin ? (id) => `/admin/api/conversations/${id}` : (id) => `/api/chat/conversations/${id}`;

    const fetchConversations = useCallback(async () => {
         const token = localStorage.getItem('token');
         try {
             const res = await fetch(apiUrl(convEndpoint), {
                 headers: { 'Authorization': `Bearer ${token}` }
             });
             if (res.ok) setConversations(await res.json());
         } catch (e) { errorTracker.reportError(e); }
    }, [convEndpoint]);

    useEffect(() => {
        fetchConversations();
    }, [fetchConversations]);

    const { messages, sendMessage, status, conversationId, setConversationId, clearMessages, setMessages } = useAgentSocket(endpoint, localStorage.getItem('token'), fetchConversations);

    const loadConversation = async (id) => {
        setIsSidebarOpen(false);
        setConversationId(id);
        const token = localStorage.getItem('token');
        try {
            const res = await fetch(apiUrl(historyEndpoint(id)), {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
                const data = await res.json();
                setMessages(data.messages || []);
                setConversationId(data.conversation_id);
            }
        } catch (e) { errorTracker.reportError(e); }
    };

    const handleNewChat = () => {
        clearMessages();
        setConversationId(null);
        setIsSidebarOpen(false);
        setIsMenuOpen(false);
    };

    useEffect(() => {
        const storedTheme = localStorage.getItem('theme');
        const initialTheme = storedTheme === 'light' ? 'light' : 'dark';
        setTheme(initialTheme);
    }, []);

    useEffect(() => {
        if (typeof document === 'undefined') return;
        document.documentElement.dataset.theme = theme;
        document.documentElement.dir = 'rtl';
        localStorage.setItem('theme', theme);
    }, [theme]);

    useEffect(() => {
        const handleOutsideClick = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setIsMenuOpen(false);
            }
        };
        document.addEventListener('mousedown', handleOutsideClick);
        return () => document.removeEventListener('mousedown', handleOutsideClick);
    }, []);

    const handleToggleTheme = () => {
        setTheme((prevTheme) => (prevTheme === 'dark' ? 'light' : 'dark'));
        setIsMenuOpen(false);
    };

    const getStatusText = (st) => {
        switch (st) {
            case 'connected': return 'متصل';
            case 'connecting': return 'جاري الاتصال...';
            case 'disconnected': return 'غير متصل';
            case 'error': return 'خطأ في الاتصال';
            default: return st;
        }
    };

    return (
        <div className="app-container">
            <div className="header">
                <div className="header-title">
                     <button
                        className="header-menu-btn"
                        onClick={() => setIsAgentSidebarOpen(prev => !prev)}
                        title="فريق العملاء"
                        style={{ marginLeft: '0.5rem', background: isAgentSidebarOpen ? 'var(--bg-color)' : 'transparent' }}
                    >
                        <i className="fas fa-robot"></i>
                    </button>
                    <h2>
                        {user.is_admin ? 'OVERMIND CLI' : 'Overmind Education'}
                        <span className="header-status">
                            {status === 'connected' ?
                                <span className="status-online">● {getStatusText(status)}</span> :
                                <span className="status-offline">● {getStatusText(status)}</span>
                            }
                        </span>
                    </h2>
                </div>
                <div className="header-actions" ref={menuRef}>
                    <button
                        className="header-menu-btn"
                        onClick={() => setIsMenuOpen((prev) => !prev)}
                    >
                        <i className="fas fa-ellipsis-v"></i>
                    </button>
                    {isMenuOpen && (
                        <div className="header-menu">
                            <button className="header-menu-item" onClick={handleNewChat}>
                                <i className="fas fa-plus"></i>
                                <span>محادثة جديدة</span>
                            </button>
                            <button className="header-menu-item" onClick={() => setIsSidebarOpen(true)}>
                                <i className="fas fa-history"></i>
                                <span>المحادثات السابقة</span>
                            </button>
                            <button className="header-menu-item" onClick={handleToggleTheme}>
                                <i className={`fas ${theme === 'dark' ? 'fa-sun' : 'fa-moon'}`}></i>
                                <span>{theme === 'dark' ? 'الوضع النهاري' : 'الوضع المظلم'}</span>
                            </button>
                            <button className="header-menu-item" onClick={onLogout}>
                                <i className="fas fa-sign-out-alt"></i>
                                <span>تسجيل الخروج</span>
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <div className="dashboard-layout">
                {/* Agent Sidebar (Left in RTL) */}
                <div className={`agent-sidebar ${isAgentSidebarOpen ? 'open' : ''}`}>
                     <div className="agent-sidebar-header">
                        <h3>فريق العملاء</h3>
                        <button onClick={() => setIsAgentSidebarOpen(false)} style={{background:'none', border:'none', fontSize:'1.2rem', cursor:'pointer'}}>
                            <i className="fas fa-times"></i>
                        </button>
                     </div>
                     <div style={{ padding: '0.5rem' }}>
                        <AgentTimeline />
                     </div>
                </div>

                <div className={`sidebar-overlay ${isSidebarOpen ? 'visible' : ''}`} onClick={() => setIsSidebarOpen(false)}></div>
                <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
                     <div className="sidebar-header">
                        <h3>المحادثات</h3>
                        <button className="close-sidebar-btn" onClick={() => setIsSidebarOpen(false)} style={{background:'none', border:'none', fontSize:'1.2rem', cursor:'pointer'}}>
                            <i className="fas fa-times"></i>
                        </button>
                     </div>
                     <div className="conversation-list">
                         {conversations.map(conv => (
                             <div
                                 key={conv.conversation_id}
                                 className={`conversation-item ${conversationId === conv.conversation_id ? 'active' : ''}`}
                                 onClick={() => loadConversation(conv.conversation_id)}
                             >
                                 <i className="fas fa-comment-alt"></i>
                                 {conv.title || `محادثة ${conv.conversation_id.substr(0,8)}...`}
                             </div>
                         ))}
                     </div>
                </div>

                <div className="chat-area">
                    <ChatInterface
                        messages={messages}
                        onSendMessage={sendMessage}
                        status={status}
                        user={user}
                    />
                </div>
            </div>
        </div>
    );
};

const App = () => {
    const [token, setToken] = useState(null);
    const [user, setUser] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    useEffect(() => {
        const storedToken = localStorage.getItem('token');
        if (storedToken) setToken(storedToken);
        else setIsLoading(false);
    }, []);

    useEffect(() => {
        const fetchUser = async () => {
            if (token) {
                try {
                    const response = await fetch(apiUrl('/api/security/user/me'), {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    if (response.ok) {
                        setUser(await response.json());
                    } else {
                        logout();
                    }
                } catch (error) {
                    errorTracker.reportError(error, { message: "Failed to fetch user" });
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

    const handleLogin = (newToken, userData) => {
        localStorage.setItem('token', newToken);
        setToken(newToken);
        setUser(userData);
    };

    const logout = () => {
        localStorage.removeItem('token');
        setToken(null);
        setUser(null);
        window.location.reload();
    };

    if (isLoading) return <div className="loading-screen"><i className="fas fa-circle-notch fa-spin"></i><h2>جاري تهيئة النظام...</h2></div>;
    if (!token || !user) return <AuthScreen onLogin={handleLogin} />;

    return <DashboardLayout user={user} onLogout={logout} />;
};

export default function CogniForgeApp() {
    return (
        <ErrorBoundary>
            <App />
        </ErrorBoundary>
    );
}
