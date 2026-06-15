import { useState, useRef, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import { Mic, MicOff, X, Loader2 } from "lucide-react";

const LANGS = [
  { code: "en-IN", label: "EN", flag: "🇬🇧" },
  { code: "hi-IN", label: "HI", flag: "🇮🇳" },
];

export default function VoiceAssistant({ onSendToChat }) {
  const location = useLocation();
  const navigate = useNavigate();

  const [state, setState] = useState("idle"); // idle | listening | processing
  const [lang, setLang] = useState("en-IN");
  const [transcript, setTranscript] = useState("");
  const [showLangMenu, setShowLangMenu] = useState(false);
  const recognitionRef = useRef(null);

  const isSupported = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

  const startListening = () => {
    if (!isSupported) {
      toast.error("Voice input is not supported in this browser. Try Chrome or Edge.");
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = lang;
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => setState("listening");
    recognition.onerror = (e) => {
      setState("idle");
      if (e.error !== "no-speech") toast.error("Voice error: " + e.error);
    };
    recognition.onend = () => {
      if (state === "listening") setState("idle");
    };
    recognition.onresult = async (event) => {
      const text = event.results[0][0].transcript;
      setTranscript(text);
      setState("processing");
      try {
        const r = await api.post("/ai/voice-command", {
          transcript: text,
          language: lang,
          current_module: location.pathname,
        });
        if (r.data.intent === "navigate" && r.data.route) {
          toast.success(`🎤 "${text}" → Navigating...`, { duration: 2000 });
          setTimeout(() => navigate(r.data.route), 500);
        } else if (r.data.intent === "chat" || r.data.intent === "action") {
          toast.info(`🎤 "${text}"`, { duration: 2500 });
          onSendToChat?.(r.data.message || text);
        } else {
          onSendToChat?.(text);
        }
      } catch {
        onSendToChat?.(text);
      } finally {
        setTimeout(() => { setState("idle"); setTranscript(""); }, 1500);
      }
    };

    recognition.start();
    recognitionRef.current = recognition;
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setState("idle");
  };

  const handleClick = () => {
    if (state === "idle") startListening();
    else stopListening();
  };

  // Pulse ring animation CSS
  const pulseRings = state === "listening" ? (
    <>
      <div className="absolute inset-0 rounded-full bg-red-500/30 animate-ping" />
      <div className="absolute -inset-2 rounded-full bg-red-500/15 animate-ping" style={{ animationDelay: "0.3s" }} />
    </>
  ) : state === "idle" ? (
    <div className="absolute inset-0 rounded-full bg-yellow-400/20 animate-ping" style={{ animationDuration: "3s" }} />
  ) : null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
      {/* Transcript bubble */}
      {transcript && state === "processing" && (
        <div className="bg-zinc-900 border border-zinc-700 text-white text-xs px-3 py-2 max-w-48 text-right shadow-xl animate-fade-in">
          <div className="font-mono text-[9px] text-zinc-500 uppercase mb-1">Heard:</div>
          <div className="text-zinc-200">{transcript}</div>
        </div>
      )}

      {/* Language selector */}
      <div className="flex flex-col items-end gap-1">
        {showLangMenu && (
          <div className="bg-zinc-900 border border-zinc-700 shadow-xl overflow-hidden">
            {LANGS.map(l => (
              <button
                key={l.code}
                onClick={() => { setLang(l.code); setShowLangMenu(false); }}
                className={`flex items-center gap-2 px-3 py-2 text-xs font-mono w-full text-left transition-colors hover:bg-zinc-800 ${
                  lang === l.code ? "text-yellow-400 bg-yellow-400/10" : "text-zinc-400"
                }`}
              >
                <span>{l.flag}</span>
                <span>{l.label}</span>
              </button>
            ))}
          </div>
        )}
        <button
          onClick={() => setShowLangMenu(!showLangMenu)}
          className="px-2 py-1 bg-zinc-900 border border-zinc-700 hover:border-yellow-400 text-[9px] font-mono text-zinc-400 hover:text-yellow-400 transition-colors"
        >
          {LANGS.find(l => l.code === lang)?.flag} {LANGS.find(l => l.code === lang)?.label}
        </button>
      </div>

      {/* Main voice button */}
      <div className="relative">
        {pulseRings}
        <button
          onClick={handleClick}
          disabled={!isSupported}
          title={
            !isSupported ? "Voice not supported in this browser" :
            state === "idle" ? "Voice Assistant (Hindi/English)" :
            state === "listening" ? "Listening... click to stop" :
            "Processing..."
          }
          className={`relative w-14 h-14 rounded-full flex items-center justify-center shadow-2xl transition-all duration-200 ${
            state === "listening"
              ? "bg-red-500 hover:bg-red-600 scale-110"
              : state === "processing"
              ? "bg-yellow-500 cursor-wait"
              : "bg-yellow-400 hover:bg-yellow-300 hover:scale-105"
          } ${!isSupported ? "opacity-40 cursor-not-allowed" : ""}`}
        >
          {state === "processing" ? (
            <Loader2 className="w-6 h-6 text-black animate-spin" />
          ) : state === "listening" ? (
            <MicOff className="w-6 h-6 text-white" />
          ) : (
            <Mic className="w-6 h-6 text-black" />
          )}
        </button>
      </div>

      {/* Status label */}
      <div className="font-mono text-[8px] uppercase tracking-widest text-center" style={{ minWidth: 56 }}>
        {state === "listening" ? (
          <span className="text-red-400 animate-pulse">● Listening</span>
        ) : state === "processing" ? (
          <span className="text-yellow-400">Processing</span>
        ) : (
          <span className="text-zinc-600">Voice AI</span>
        )}
      </div>
    </div>
  );
}
