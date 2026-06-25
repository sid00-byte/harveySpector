"use client";

import { useState, useRef, useEffect } from "react";
import styles from "./chat.module.css";

interface Citation {
  raw_citation: string;
  status: "VERIFIED" | "APPROXIMATE" | "UNVERIFIED";
}

interface Message {
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  timestamp: string;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function parseCitations(text: string): string {
  return text.replace(
    /\[Section\s+([^\]]+)\]/g,
    '<span class="citation">[$1]</span>'
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hello! I'm your Companies Act 2013 compliance assistant. Ask me anything about the Act — I'll provide precise section, page, and line references for every answer.\n\nFor example, try:\n• \"What are the requirements for appointing a director?\"\n• \"Explain Section 185 on loans to directors\"\n• \"What forms are needed for share transfer?\"",
      citations: [],
      timestamp: "2026-06-25T00:00:00.000Z",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [caseId, setCaseId] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("caseId") || `case-${Date.now()}`;
    setCaseId(id);

    if (params.get("caseId")) {
      fetch(`${API_URL}/api/v1/chat/history/${id}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.messages && data.messages.length > 0) {
            const parsed = data.messages.map((m: any) => ({
              role: m.role,
              content: m.content,
              citations: m.citations || [],
              timestamp: m.timestamp,
            }));
            setMessages(parsed);
          }
        })
        .catch((e) => console.error("Error loading chat history:", e));
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    const userMessage: Message = {
      role: "user",
      content: msg,
      citations: [],
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: caseId,
          message: msg,
          history: messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
      });

      if (!res.ok) throw new Error("Chat failed");
      const data = await res.json();

      const assistantMessage: Message = {
        role: "assistant",
        content: data.reply,
        citations: data.citations || [],
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I'm unable to connect to the backend right now. Please ensure the FastAPI server is running at " +
            API_URL +
            " and try again.",
          citations: [],
          timestamp: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={styles.chatPage}>
      {/* Sidebar */}
      <aside className={styles.sidebar}>
        <div className={styles.sidebarHeader}>
          <h2 className={styles.sidebarTitle}>⚖️ Legal Chat</h2>
        </div>
        <div className={styles.sidebarContent}>
          <div className={styles.quickActions}>
            <h3 className={styles.quickTitle}>Quick Questions</h3>
            {[
              "Requirements for board meeting",
              "Director appointment process",
              "CSR compliance under Section 135",
              "Annual return filing requirements",
              "Related party transaction rules",
            ].map((q) => (
              <button
                key={q}
                className={styles.quickBtn}
                onClick={() => { setInput(q); inputRef.current?.focus(); }}
              >
                {q}
              </button>
            ))}
          </div>
          <div className={styles.sidebarInfo}>
            <div className={styles.infoBadge}>
              <span className={styles.infoIcon}>📚</span>
              <span>470 Sections</span>
            </div>
            <div className={styles.infoBadge}>
              <span className={styles.infoIcon}>📖</span>
              <span>29 Chapters</span>
            </div>
            <div className={styles.infoBadge}>
              <span className={styles.infoIcon}>📋</span>
              <span>7 Schedules</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Chat Area */}
      <main className={styles.chatMain}>
        <div className={styles.messagesContainer}>
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`${styles.message} ${
                msg.role === "user" ? styles.userMessage : styles.assistantMessage
              }`}
              id={`message-${idx}`}
            >
              <div className={styles.messageAvatar}>
                {msg.role === "user" ? "👤" : "⚖️"}
              </div>
              <div className={styles.messageBubble}>
                <div
                  className={styles.messageContent}
                  dangerouslySetInnerHTML={{
                    __html: parseCitations(
                      msg.content.replace(/\n/g, "<br />")
                    ),
                  }}
                />
                {msg.citations.length > 0 && (
                  <div className={styles.citationBar}>
                    <span className={styles.citationLabel}>Citations:</span>
                    {msg.citations.map((c, ci) => (
                      <span
                        key={ci}
                        className={`${styles.citationBadge} ${
                          c.status === "VERIFIED"
                            ? styles.citationVerified
                            : c.status === "APPROXIMATE"
                            ? styles.citationApproximate
                            : styles.citationUnverified
                        }`}
                      >
                        {c.status === "VERIFIED" ? "✓" : c.status === "APPROXIMATE" ? "≈" : "?"}{" "}
                        {c.raw_citation}
                      </span>
                    ))}
                  </div>
                )}
                <span className={styles.messageTime}>{formatTime(msg.timestamp)}</span>
              </div>
            </div>
          ))}

          {loading && (
            <div className={`${styles.message} ${styles.assistantMessage}`}>
              <div className={styles.messageAvatar}>⚖️</div>
              <div className={styles.messageBubble}>
                <div className={styles.typingIndicator}>
                  <span className={styles.typingDot} />
                  <span className={styles.typingDot} />
                  <span className={styles.typingDot} />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className={styles.inputContainer}>
          <div className={styles.inputWrapper}>
            <textarea
              ref={inputRef}
              className={styles.chatInput}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about any section of the Companies Act, 2013..."
              rows={1}
              disabled={loading}
              id="chat-input"
            />
            <button
              className={styles.sendBtn}
              onClick={handleSend}
              disabled={!input.trim() || loading}
              id="chat-send"
              aria-label="Send message"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path
                  d="M18 2L9 11M18 2L12 18L9 11M18 2L2 8L9 11"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
          <p className={styles.inputHint}>
            Press Enter to send · Shift+Enter for new line · All answers cite exact Act references
          </p>
        </div>
      </main>
    </div>
  );
}
