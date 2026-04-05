import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const preprocessMath = (content) => {
    if (!content) return "";
    let processed = content.replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$');
    processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$');
    return processed;
};

const Markdown = memo(({ content }) => {
    const safeContent = (content || "");
    const processedContent = preprocessMath(safeContent);

    return (
        <div className="markdown-content">
            <ReactMarkdown
                remarkPlugins={[remarkMath]}
                rehypePlugins={[rehypeKatex]}
            >
                {processedContent}
            </ReactMarkdown>
        </div>
    );
});
Markdown.displayName = 'Markdown';

export const ChatInterface = ({ messages, onSendMessage, status, user }) => {
    const [input, setInput] = useState('');
    const messagesEndRef = useRef(null);
    const messagesContainerRef = useRef(null);
    const [autoScroll, setAutoScroll] = useState(true);

    const scrollToBottom = useCallback(() => {
        if (messagesEndRef.current) {
             messagesEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
        }
    }, []);

    useEffect(() => {
        if (autoScroll) {
            const container = messagesContainerRef.current;
            if (container) {
                const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150;
                if (isNearBottom) {
                    container.scrollTop = container.scrollHeight;
                }
            }
        }
    }, [messages, autoScroll]);

    const handleScroll = () => {
        const container = messagesContainerRef.current;
        if (container) {
            const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 50;
            setAutoScroll(isNearBottom);
        }
    };

    const handleSend = () => {
        if (!input.trim()) return;
        setAutoScroll(true);
        onSendMessage(input, {});
        setInput('');
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="chat-container">
            <div className="messages" ref={messagesContainerRef} onScroll={handleScroll}>
                {messages.length === 0 ? (
                    <div className="welcome-message" style={{ textAlign: 'center', marginTop: '20vh', color: 'var(--text-secondary)' }}>
                         <i className={`fas ${user.is_admin ? 'fa-brain' : 'fa-graduation-cap'}`} style={{fontSize: '3em', color: 'var(--primary-color)', marginBottom: '20px'}}></i>
                        <h3>{user.is_admin ? 'System Ready' : 'مرحباً بك'}</h3>
                        <p>{user.is_admin ? 'The Overmind is listening.' : 'اسألني أي شيء يخص دراستك.'}</p>
                    </div>
                ) : (
                    messages.map((msg, idx) => (
                        <div key={msg.id || idx} className={`message ${msg.role}`}>
                            <div className="message-bubble" style={{ position: 'relative', paddingBottom: msg.role === 'assistant' ? '24px' : undefined }}>
                                {msg.role === 'assistant' ? <Markdown content={msg.content} /> : msg.content}
                                {msg.role === 'assistant' && (
                                    <button
                                        className="copy-button"
                                        onClick={() => {
                                            navigator.clipboard.writeText(msg.content).then(() => {
                                                const btn = document.getElementById(`copy-btn-${msg.id || idx}`);
                                                if (btn) {
                                                    const icon = btn.querySelector('i');
                                                    icon.className = 'fas fa-check';
                                                    setTimeout(() => {
                                                        icon.className = 'far fa-copy';
                                                    }, 2000);
                                                }
                                            });
                                        }}
                                        id={`copy-btn-${msg.id || idx}`}
                                        title="نسخ النص"
                                        style={{
                                            position: 'absolute',
                                            bottom: '4px',
                                            left: '8px',
                                            background: 'transparent',
                                            border: 'none',
                                            color: 'var(--text-secondary)',
                                            cursor: 'pointer',
                                            padding: '4px',
                                            borderRadius: '4px',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            opacity: 0.6,
                                            transition: 'opacity 0.2s, transform 0.1s',
                                            fontSize: '0.85rem'
                                        }}
                                        onMouseEnter={(e) => e.currentTarget.style.opacity = '1'}
                                        onMouseLeave={(e) => e.currentTarget.style.opacity = '0.6'}
                                        onMouseDown={(e) => e.currentTarget.style.transform = 'scale(0.9)'}
                                        onMouseUp={(e) => e.currentTarget.style.transform = 'scale(1)'}
                                    >
                                        <i className="far fa-copy"></i>
                                    </button>
                                )}
                            </div>
                        </div>
                    ))
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="input-area-wrapper">
                 <div className="input-area">
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder={"اكتب سؤالك أو مهمتك..."}
                        rows="1"
                    />
                    <button onClick={handleSend} disabled={!input.trim()}>
                        <i className="fas fa-arrow-up"></i>
                    </button>
                 </div>
            </div>
        </div>
    );
};
