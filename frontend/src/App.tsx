import { useEffect, useRef, useState } from "react";
import "./App.css";
import { fetchAirports, postChat } from "./api";
import type { Airport, ChatMessage } from "./types";
import ChatThread from "./components/ChatThread";
import AirportSidebar from "./components/AirportSidebar";

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export default function App() {
  const [airports, setAirports] = useState<Airport[]>([]);
  const [airportsLoading, setAirportsLoading] = useState(true);
  const [airportsError, setAirportsError] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  // Off by default so replies don't start talking unexpectedly on load.
  const [voiceOutput, setVoiceOutput] = useState(false);
  const speechSupported = typeof window !== "undefined" && "speechSynthesis" in window;
  // Chrome silently drops speech if the utterance object is garbage-collected
  // before it finishes -- keep a live reference so that can't happen.
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    fetchAirports()
      .then((data) => setAirports(data))
      .catch((err) => setAirportsError(err instanceof Error ? err.message : String(err)))
      .finally(() => setAirportsLoading(false));
  }, []);

  async function handleSend(text: string) {
    const userMsg: ChatMessage = { id: newId(), role: "user", text };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);
    try {
      const resp = await postChat({ message: text, conversation_id: conversationId });
      setConversationId(resp.conversation_id);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "assistant", text: resp.reply, breakdown: resp.breakdown },
      ]);
      // Speak only the prose reply, never the structured breakdown JSON.
      if (voiceOutput && speechSupported) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(resp.reply);
        utteranceRef.current = utterance; // keep alive -- see comment above
        utterance.onend = () => {
          utteranceRef.current = null;
        };
        window.speechSynthesis.speak(utterance);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          text: `Something went wrong talking to the backend: ${
            err instanceof Error ? err.message : String(err)
          }`,
          error: true,
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>Airport Investment Intelligence Agent</h1>
        <p>
          Chat with a deterministic-scoring-backed agent about US airport terminal/capacity
          expansion candidates. Scores come from real computed KPIs, not LLM guesses -- expand
          "Show the math" under any answer to audit the numbers.
        </p>
        {speechSupported && (
          <label className="voice-output-toggle">
            <input
              type="checkbox"
              checked={voiceOutput}
              onChange={(e) => {
                setVoiceOutput(e.target.checked);
                if (!e.target.checked) window.speechSynthesis.cancel();
              }}
            />
            Read replies aloud
          </label>
        )}
      </header>
      <div className="app-body">
        <AirportSidebar airports={airports} loading={airportsLoading} error={airportsError} />
        <ChatThread messages={messages} onSend={handleSend} sending={sending} />
      </div>
    </div>
  );
}
