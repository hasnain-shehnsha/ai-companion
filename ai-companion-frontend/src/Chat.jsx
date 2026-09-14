import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import api from "./api";
import { Send, LogOut, Loader2, Plus, MessageSquare, Menu, Trash2, Brain } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs) {
  return twMerge(clsx(inputs));
}

export default function Chat({ token, onLogout }) {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [usageData, setUsageData] = useState(null);
  const [userProfile, setUserProfile] = useState(null);
  const messagesEndRef = useRef(null);

  const fetchUsage = async () => {
    if (!token) return;
    try {
      const res = await api.get(`/users/me/usage`);
      setUsageData(res.data);
    } catch (err) {
      console.error("Failed to fetch usage", err);
    }
  };

  useEffect(() => {
    if (token) {
      fetchUsage();
      api.get('/users/me').then(res => setUserProfile(res.data)).catch(err => console.error(err));
    } else {
      setUserProfile(null);
    }
  }, [token]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    async function fetchSessions() {
      if (!token) {
        setSessions([]);
        setActiveSessionId(null);
        setMessages([
          {
            id: 1,
            role: "assistant",
            content:
              "Hello. I am your AI Companion. How can I help you today? (Free Mode)",
          },
        ]);
        return;
      }
      try {
        const res = await api.get(`/chat/sessions`);
        setSessions(res.data);
        if (res.data.length > 0) {
          setActiveSessionId(res.data[0].id);
        } else {
          setMessages([
            {
              id: Date.now(),
              role: "assistant",
              content:
                "Hello! I'm thrilled to be your new Premium AI Companion. What's on your mind today?",
            },
          ]);
        }
      } catch (err) {
        console.error("Failed to fetch sessions", err);
      }
    }
    fetchSessions();
  }, [token]);

  useEffect(() => {
    async function fetchMessages() {
      if (!activeSessionId) return;
      try {
        const res = await api.get(`/chat/sessions/${activeSessionId}/messages`);
        if (res.data.length === 0) {
          setMessages([
            {
              id: Date.now(),
              role: "assistant",
              content:
                "Hello! I'm your AI Companion. How can I help you today?",
            },
          ]);
        } else {
          setMessages(res.data);
        }
      } catch (err) {
        console.error("Failed to fetch messages", err);
      }
    }
    fetchMessages();
  }, [activeSessionId]);

  const handleNewConversation = async () => {
    if (!token) {
      navigate("/login");
      return;
    }
    if (isCreatingSession) return;
    setIsCreatingSession(true);

    try {
      const res = await api.post(`/chat/sessions`);
      const newSession = res.data;
      setSessions((prev) => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      setMessages([
        {
          id: Date.now(),
          role: "assistant",
          content: "Hello! I'm your AI Companion. How can I help you today?",
        },
      ]);
      setIsSidebarOpen(false);
    } catch (err) {
      console.error(err);
    } finally {
      setIsCreatingSession(false);
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this conversation?")) return;
    try {
      await api.delete(`/chat/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setMessages([
          {
            id: Date.now(),
            role: "assistant",
            content: "Conversation deleted. Please start a new one.",
          },
        ]);
      }
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const handleDeleteMessage = async (messageId) => {
    if (!token) return; // Free mode messages aren't saved anyway
    try {
      // Optimistic UI update
      setMessages((prev) => prev.filter((m) => m.id !== messageId));
      await api.delete(`/chat/messages/${messageId}`);
    } catch (err) {
      console.error("Failed to delete message", err);
    }
  };

  const handleResetData = async () => {
    if (!window.confirm("WARNING: This will permanently delete all your chat history, memory facts, scheduled messages, and reminders. The AI will forget everything about you. Are you sure you want to proceed?")) {
      return;
    }
    
    try {
      await api.post('/users/me/reset');
      setSessions([]);
      setActiveSessionId(null);
      setMessages([
        {
          id: Date.now(),
          role: "assistant",
          content: "Brain completely wiped. Hello again! I am your AI Companion. What's on your mind today?",
        },
      ]);
      alert("AI brain successfully reset.");
    } catch (err) {
      console.error("Failed to reset data", err);
      alert("Failed to reset data. Please try again.");
    }
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    let currentSessionId = activeSessionId;
    if (!currentSessionId && token) {
      try {
        const res = await api.post(`/chat/sessions`);
        currentSessionId = res.data.id;
        setSessions((prev) => [res.data, ...prev]);
        setActiveSessionId(currentSessionId);
      } catch (err) {
        console.error(err);
        return;
      }
    }

    const userMsg = input.trim();
    setInput("");

    const tempUserMsgId = Date.now().toString();
    setMessages((prev) => [
      ...prev,
      { id: tempUserMsgId, role: "user", content: userMsg },
    ]);
    setLoading(true);

    try {
      const recentHistory = messages.map((msg) => ({
        role: msg.role,
        content: msg.content,
      }));

      const response = await api.post("/chat/", {
        session_id: currentSessionId,
        message: userMsg,
        chat_history: recentHistory,
      });
      
      setMessages((prev) => {
        // Replace the temporary user message id with the real one from DB
        const updated = prev.map(m => 
          m.id === tempUserMsgId && response.data.user_message_id ? { ...m, id: response.data.user_message_id } : m
        );
        return [
          ...updated,
          {
            id: response.data.ai_message_id || (Date.now() + 1).toString(),
            role: "assistant",
            content: response.data.response,
            extracted_facts: response.data.extracted_facts,
            memory_error: response.data.memory_error,
          }
        ];
      });

      if (token) {
        api
          .get(`/chat/sessions`)
          .then((res) => setSessions(res.data));
        fetchUsage();
      }
    } catch (err) {
      console.error("Chat message error:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content:
            "Sorry, I encountered an error communicating with my neural core.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full bg-[var(--bg-obsidian)] text-[var(--text-primary)] overflow-hidden">
      {/* Mobile Sidebar Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed md:relative z-50 w-64 h-full border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] flex flex-col transition-transform duration-300",
          isSidebarOpen
            ? "translate-x-0"
            : "-translate-x-full md:translate-x-0",
        )}
      >
        <div className="p-4 border-b border-[var(--border-subtle)]">
          <button
            onClick={handleNewConversation}
            disabled={isCreatingSession}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {isCreatingSession ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            New Conversation
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {sessions.map((session) => (
            <button
              key={session.id}
              onClick={() => {
                setActiveSessionId(session.id);
                setIsSidebarOpen(false);
              }}
              className={cn(
                "w-full text-left px-3 py-2.5 rounded-lg text-sm flex items-center justify-between gap-3 transition-colors group",
                activeSessionId === session.id
                  ? "bg-[var(--bg-obsidian)] text-[var(--text-primary)]"
                  : "text-[var(--text-muted)] hover:bg-[var(--bg-obsidian)]",
              )}
            >
              <div className="flex items-center gap-3 truncate">
                <MessageSquare className="w-4 h-4 shrink-0" />
                <span className="truncate">{session.title}</span>
              </div>
              <button
                onClick={(e) => handleDeleteSession(e, session.id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-all shrink-0"
                title="Delete Conversation"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </button>
          ))}
        </div>
        <div className="p-4 border-t border-[var(--border-subtle)] flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-[var(--accent-terracotta)] to-[var(--accent-amber)] flex items-center justify-center text-black font-bold uppercase">
                {userProfile ? userProfile.first_name[0] : (token ? "U" : "?")}
              </div>
              <span className="capitalize">{userProfile ? userProfile.tier.toLowerCase() : (token ? "Loading..." : "Free")}</span>
            </div>
            {token && (
              <button
                onClick={onLogout}
                className="text-[var(--text-muted)] hover:text-[var(--accent-terracotta)] transition-colors p-2"
                title="Log Out"
              >
                <LogOut className="w-5 h-5" />
              </button>
            )}
          </div>
          {token && (
            <button
              onClick={handleResetData}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-xs font-medium text-red-400 border border-red-500/20 hover:bg-red-500/10 transition-colors"
            >
              <Brain className="w-3.5 h-3.5" />
              Reset AI Brain
            </button>
          )}
        </div>
      </aside>

      {/* Main Chat Area */}
      <div className="flex flex-col flex-1 h-screen relative min-w-0">
        {/* Header */}
        <header className="glass-panel sticky top-0 z-10 px-4 sm:px-6 py-4 flex items-center justify-between border-b border-[var(--border-subtle)]">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(true)}
              className="md:hidden text-[var(--text-primary)] p-1 mr-1"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-[var(--accent-terracotta)] to-[var(--accent-amber)] p-[2px] hidden sm:block">
              <div className="w-full h-full rounded-full bg-[var(--bg-surface)] flex items-center justify-center">
                <span className="font-semibold text-sm">AI</span>
              </div>
            </div>
            <div>
              <h2 className="font-medium text-lg leading-tight">Companion</h2>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                <span className="text-xs text-[var(--text-muted)]">
                  Neural Core Online
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {!token && (
              <div className="flex items-center gap-3">
                <button
                  onClick={() => navigate("/login")}
                  className="hidden sm:block px-4 py-2 rounded-xl text-sm font-medium text-[var(--text-primary)] border border-[var(--border-subtle)] hover:bg-[var(--bg-surface)] transition-colors"
                >
                  Log In
                </button>
                <button
                  onClick={() => navigate("/register")}
                  className="px-4 py-2 rounded-xl text-sm font-medium text-black bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] hover:opacity-90 transition-opacity"
                >
                  Go Premium
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Chat Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          <div className="max-w-3xl mx-auto space-y-6">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex w-full animate-enter group",
                  msg.role === "user" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "relative max-w-[90%] sm:max-w-[75%] px-4 sm:px-5 py-3 sm:py-3.5 rounded-2xl leading-relaxed shadow-lg overflow-visible",
                    msg.role === "user"
                      ? "bg-gradient-to-br from-[var(--accent-terracotta)] to-[var(--accent-amber)] text-black rounded-tr-sm"
                      : "glass-panel text-[var(--text-primary)] rounded-tl-sm markdown-prose",
                  )}
                >
                  <button
                    onClick={() => handleDeleteMessage(msg.id)}
                    className={cn(
                      "absolute top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-2 rounded-full bg-[var(--bg-obsidian)] text-[var(--text-muted)] hover:text-red-400 shadow-md border border-[var(--border-subtle)] z-10",
                      msg.role === "user" ? "-left-12" : "-right-12"
                    )}
                    title="Delete message"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                  {msg.role === "user" ? (
                    <span className="whitespace-pre-wrap">{msg.content}</span>
                  ) : (
                    <div className="flex flex-col">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                      {(msg.extracted_facts || msg.memory_error) && (
                        <div className="mt-3 pt-3 border-t border-[var(--glass-border)] text-xs flex flex-col gap-1.5 opacity-90">
                          {msg.extracted_facts &&
                            msg.extracted_facts.map((fact, idx) => (
                              <span
                                key={idx}
                                className="text-emerald-400 flex items-start gap-1"
                              >
                                ✓ Saved in memory:{" "}
                                {fact.replace(/^[-*]\s*/, "")}
                              </span>
                            ))}
                          {msg.memory_error && (
                            <span className="text-red-400 flex items-start gap-1">
                              ! Memory error: {msg.memory_error}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex w-full justify-start animate-enter">
                <div className="glass-panel rounded-2xl rounded-tl-sm px-5 py-3.5 flex items-center gap-3">
                  <Loader2 className="w-4 h-4 animate-spin text-[var(--accent-amber)]" />
                  <span className="text-sm text-[var(--text-muted)]">
                    Synthesizing response...
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </main>

        {/* Input Area */}
        <footer className="p-4 sm:p-6 glass-panel border-t border-[var(--border-subtle)] bg-[var(--bg-obsidian)]">
          <div className="max-w-3xl mx-auto">
            <form onSubmit={handleSend} className="relative flex items-center">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Message your companion..."
                className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded-full py-3.5 sm:py-4 pl-5 sm:pl-6 pr-12 sm:pr-14 outline-none focus:border-[var(--accent-amber)] transition-colors shadow-inner text-sm sm:text-base"
                disabled={loading}
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                className="absolute right-2 w-8 h-8 sm:w-10 sm:h-10 flex items-center justify-center rounded-full bg-gradient-to-r from-[var(--accent-terracotta)] to-[var(--accent-amber)] text-black hover:opacity-90 transition-opacity disabled:opacity-50 disabled:grayscale"
              >
                <Send className="w-4 h-4 ml-0.5" />
              </button>
            </form>
            <div className="text-center mt-2 sm:mt-3 text-[10px] sm:text-xs text-[var(--text-muted)]">
              AI can make mistakes. Remember to verify critical information.
            </div>
          </div>
        </footer>
      </div>

      {/* Right Sidebar - Usage Dashboard (Premium only) */}
      {token && (
        <aside className="hidden xl:flex flex-col w-72 h-screen border-l border-[var(--border-subtle)] bg-[var(--bg-surface)] p-5 overflow-y-auto">
          <h3 className="font-semibold text-lg mb-6 flex items-center gap-2">
            <span className="text-xl">📊</span> Usage Metrics
          </h3>
          
          {usageData ? (
            <div className="space-y-6">
              <div className="glass-panel p-4 rounded-xl">
                <div className="text-sm text-[var(--text-muted)] mb-1">Estimated Cost</div>
                <div className="text-2xl font-bold text-[var(--accent-amber)]">
                  ${usageData.total_cost.toFixed(5)}
                </div>
              </div>
              
              <div className="glass-panel p-4 rounded-xl">
                <div className="text-sm text-[var(--text-muted)] mb-1">Total Tokens</div>
                <div className="text-xl font-semibold">
                  {usageData.total_tokens.toLocaleString()}
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">By Channel</h4>
                <div className="space-y-3">
                  {Object.entries(usageData.breakdown).map(([channel, stats]) => (
                    <div key={channel} className="glass-panel p-3 rounded-lg text-sm">
                      <div className="capitalize font-medium mb-1 text-[var(--accent-terracotta)]">{channel}</div>
                      <div className="flex justify-between text-[var(--text-muted)]">
                        <span>Tokens:</span>
                        <span className="text-[var(--text-primary)]">{(stats.input_tokens + stats.output_tokens).toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-[var(--text-muted)]">
                        <span>Cost:</span>
                        <span className="text-[var(--text-primary)]">${stats.cost.toFixed(5)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
             <div className="flex items-center justify-center h-40">
                <Loader2 className="w-6 h-6 animate-spin text-[var(--text-muted)]" />
             </div>
          )}
        </aside>
      )}
    </div>
  );
}
