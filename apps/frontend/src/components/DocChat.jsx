import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { postDocChat } from "../api";
import { DocsIcon } from "./BrandMark";

const HISTORY_TURNS = 6;

export function DocChat({ repoId, activeDocId, activeDocTitle, onNavigateDoc, onClose }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const scrollerRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading || !repoId) return;
    setError(null);
    const nextMessages = [...messages, { role: "user", content: text }];
    setMessages(nextMessages);
    setInput("");
    setLoading(true);

    const history = nextMessages
      .slice(0, -1)
      .slice(-HISTORY_TURNS)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const data = await postDocChat(repoId, {
        message: text,
        active_doc_id: activeDocId || null,
        history,
      });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer || "",
          links: Array.isArray(data.links) ? data.links : [],
        },
      ]);
    } catch (err) {
      console.error("doc chat failed", err);
      setError(err?.response?.data?.detail || "Chat failed. Try again.");
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="chat-pane">
      <div className="chat-header">
        <div className="chat-title-row">
          <DocsIcon size={20} />
          <div className="chat-title">
            <strong>Ask the docs</strong>
            {activeDocTitle && (
              <div className="chat-subtitle" title={activeDocTitle}>
                context: {activeDocTitle}
              </div>
            )}
          </div>
        </div>
        {onClose && (
          <button className="chat-close" onClick={onClose} title="Hide chat" aria-label="Hide chat">
            ✕
          </button>
        )}
      </div>

      <div className="chat-scroll" ref={scrollerRef}>
        {messages.length === 0 && !loading && (
          <div className="chat-empty">
            Ask a question about this repo's documentation. I'll answer and link to the relevant pages.
          </div>
        )}
        {messages.map((m, i) => (
          <ChatBubble key={i} message={m} onNavigateDoc={onNavigateDoc} />
        ))}
        {loading && (
          <div className="chat-bubble assistant">
            <div className="chat-typing"><span /><span /><span /></div>
          </div>
        )}
        {error && <div className="chat-error">{error}</div>}
      </div>

      <div className="chat-input-row">
        <textarea
          ref={inputRef}
          className="chat-input"
          rows={2}
          placeholder="Ask anything about the docs…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="chat-send"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}

function flatten(children) {
  if (children == null) return "";
  if (typeof children === "string" || typeof children === "number") return String(children);
  if (Array.isArray(children)) return children.map(flatten).join("");
  if (children.props && children.props.children) return flatten(children.props.children);
  return "";
}

function ChatBubble({ message, onNavigateDoc }) {
  const isUser = message.role === "user";
  return (
    <div className={`chat-bubble ${isUser ? "user" : "assistant"}`}>
      {isUser ? (
        <div className="chat-bubble-text">{message.content}</div>
      ) : (
        <div className="chat-md">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              a({ href, children, ...props }) {
                if (href && href.startsWith("aura-doc:")) {
                  const target = href.slice("aura-doc:".length);
                  const [docId, anchor] = target.split("#");
                  return (
                    <button
                      type="button"
                      className="chat-link-pill"
                      onClick={() => onNavigateDoc?.(docId, anchor || null)}
                      title={`Open ${flatten(children)}`}
                    >
                      → {children}
                    </button>
                  );
                }
                const external = href && /^[a-z]+:\/\//i.test(href);
                return (
                  <a
                    href={href}
                    target={external ? "_blank" : undefined}
                    rel={external ? "noreferrer" : undefined}
                    {...props}
                  >
                    {children}
                  </a>
                );
              },
            }}
          >
            {message.content || ""}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );
}
