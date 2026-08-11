import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../types";
import BreakdownPanel from "./BreakdownPanel";

export default function ChatThread({
  messages,
  onSend,
  sending,
}: {
  messages: ChatMessage[];
  onSend: (text: string) => void;
  sending: boolean;
}) {
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    onSend(text);
    setDraft("");
  }

  return (
    <div className="chat-panel">
      <div className="chat-thread">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Ask about airport investment candidates, e.g.:</p>
            <ul>
              <li>"Which airports in New England are strong candidates for terminal expansion?"</li>
              <li>"Compare LA and Santa Ana airport congestion levels."</li>
              <li>"What is the percentage of long haul flights out of Anchorage airport?"</li>
              <li>"What is the unmet flight demand in SFO airport and why?"</li>
            </ul>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-message chat-message-${m.role}`}>
            <div className={`chat-bubble ${m.error ? "chat-bubble-error" : ""}`}>
              <div className="chat-role">{m.role === "user" ? "You" : "Agent"}</div>
              <div className="chat-text">{m.text}</div>
            </div>
            {m.role === "assistant" && m.breakdown && m.breakdown.length > 0 && (
              <BreakdownPanel items={m.breakdown} />
            )}
          </div>
        ))}
        {sending && (
          <div className="chat-message chat-message-assistant">
            <div className="chat-bubble chat-bubble-pending">
              <div className="chat-role">Agent</div>
              <div className="chat-text">Thinking...</div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form className="chat-input-row" onSubmit={handleSubmit}>
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about airport expansion candidates..."
          disabled={sending}
        />
        <button type="submit" disabled={sending || !draft.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
