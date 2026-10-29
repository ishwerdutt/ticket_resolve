"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Send,
  Bot,
  Clock,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  Package,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { sendChatMessage, ChatResponse } from "@/lib/api";
import { QUICK_PROMPTS } from "@/lib/constants";

interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  state?: string;
  requiresApproval?: boolean;
  time: string;
}

interface ChatPortalProps {
  token: string;
  userName: string;
}

export default function ChatPortal({ token, userName }: ChatPortalProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "init",
      sender: "bot",
      text: `Hello ${userName}! 👋 I'm Tara, your ThreadNest support assistant. How can I help you today? You can ask me to track your orders, check return policies, request a refund, or update your delivery address.`,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [currentState, setCurrentState] = useState<string>("NEW");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: String(Date.now()),
      sender: "user",
      text,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res: ChatResponse = await sendChatMessage(text, token, conversationId);
      setConversationId(res.conversation_id);
      setCurrentState(res.state);

      const botMsg: Message = {
        id: String(Date.now() + 1),
        sender: "bot",
        text: res.reply,
        state: res.state,
        requiresApproval: res.requires_approval,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: String(Date.now() + 1),
        sender: "bot",
        text: `⚠️ Error: ${err.message || "Failed to reach the support agent."}`,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const getStateBadge = (state?: string) => {
    switch (state) {
      case "AWAITING_APPROVAL":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-300">
            <Clock className="w-3 h-3" /> Awaiting Staff Approval
          </span>
        );
      case "RESOLVED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-300">
            <CheckCircle className="w-3 h-3" /> Resolved
          </span>
        );
      case "ESCALATED":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 border border-rose-300">
            <ShieldAlert className="w-3 h-3" /> Escalated to Human
          </span>
        );
      case "ACTING":
      case "GATHERING_INFO":
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 border border-indigo-300">
            <Sparkles className="w-3 h-3" /> Taking Action
          </span>
        );
      default:
        return null;
    }
  };

  // Format citations like [Return Policy § Section 2] nicely
  const renderMessageContent = (text: string) => {
    const parts = text.split(/(\[.*?§.*?\])/g);
    return (
      <div className="whitespace-pre-wrap leading-relaxed">
        {parts.map((part, index) => {
          if (part.startsWith("[") && part.includes("§") && part.endsWith("]")) {
            return (
              <span
                key={index}
                className="inline-block mx-1 px-2 py-0.5 text-xs font-semibold bg-violet-100 text-violet-800 rounded-md border border-violet-200"
              >
                📜 {part.slice(1, -1)}
              </span>
            );
          }
          return <span key={index}>{part}</span>;
        })}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-[740px] bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
      {/* Chat Header */}
      <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-indigo-700 via-indigo-600 to-violet-700 text-white shadow-sm">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center backdrop-blur-sm border border-white/30 text-xl font-bold">
              🧶
            </div>
            <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-400 border-2 border-indigo-700 rounded-full"></span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="font-semibold text-lg">Tara</h2>
              <span className="px-2 py-0.5 text-xs bg-white/20 rounded-full font-medium">
                ThreadNest AI
              </span>
            </div>
            <p className="text-xs text-indigo-200">
              Autonomous Support · Grounded in Store Policy
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {currentState && currentState !== "NEW" && (
            <div className="text-xs bg-black/20 px-3 py-1 rounded-full text-indigo-100 border border-white/10">
              Status: <span className="font-semibold text-white">{currentState}</span>
            </div>
          )}
          <button
            onClick={() => {
              setConversationId(null);
              setCurrentState("NEW");
              setMessages([
                {
                  id: "reset",
                  sender: "bot",
                  text: `Conversation reset! How can I assist you with your ThreadNest orders today, ${userName}?`,
                  time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                },
              ]);
            }}
            title="Start new conversation"
            className="p-2 hover:bg-white/10 rounded-lg transition-colors text-indigo-200 hover:text-white"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex gap-3 ${
              m.sender === "user" ? "justify-end" : "justify-start"
            }`}
          >
            {m.sender === "bot" && (
              <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shrink-0 mt-1 shadow-sm">
                <Bot className="w-4 h-4" />
              </div>
            )}

            <div
              className={`max-w-[78%] rounded-2xl px-5 py-3.5 shadow-sm text-sm ${
                m.sender === "user"
                  ? "bg-indigo-600 text-white rounded-tr-none"
                  : "bg-white text-slate-800 border border-slate-200/80 rounded-tl-none"
              }`}
            >
              {m.sender === "bot" ? (
                <>
                  {renderMessageContent(m.text)}

                  {m.requiresApproval && (
                    <div className="mt-3 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <div>
                        <span className="font-semibold">Review Pending:</span> A ThreadNest team member has been notified to confirm this action. You will receive an update once approved!
                      </div>
                    </div>
                  )}

                  <div className="mt-2.5 flex items-center justify-between text-[11px] text-slate-400">
                    <span>{m.time}</span>
                    {getStateBadge(m.state)}
                  </div>
                </>
              ) : (
                <>
                  <p className="whitespace-pre-wrap">{m.text}</p>
                  <span className="block text-right text-[11px] text-indigo-200 mt-1">
                    {m.time}
                  </span>
                </>
              )}
            </div>

            {m.sender === "user" && (
              <div className="w-8 h-8 rounded-full bg-slate-700 text-white flex items-center justify-center shrink-0 mt-1 shadow-sm font-semibold text-xs">
                {userName.charAt(0)}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 items-center text-slate-500 text-sm">
            <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-sm">
              <Bot className="w-4 h-4 animate-spin" />
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl px-4 py-2.5 text-xs shadow-sm flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse"></span>
              Tara is researching policies and executing tools...
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick Prompts Bar */}
      <div className="px-6 py-2.5 bg-slate-100 border-t border-slate-200 flex items-center gap-2 overflow-x-auto scrollbar-none">
        <span className="text-xs font-semibold text-slate-500 shrink-0 flex items-center gap-1">
          <Package className="w-3.5 h-3.5" /> Quick Actions:
        </span>
        {QUICK_PROMPTS.map((q, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(q.prompt)}
            disabled={loading}
            className="shrink-0 text-xs px-3 py-1.5 rounded-full bg-white hover:bg-indigo-50 text-slate-700 hover:text-indigo-700 border border-slate-200 shadow-sm transition-all hover:border-indigo-300 disabled:opacity-50"
          >
            <span className="mr-1">{q.icon}</span> {q.title}
          </button>
        ))}
      </div>

      {/* Input Area */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="p-4 bg-white border-t border-slate-200 flex items-center gap-3"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask Tara about your orders, returns, or refunds...`}
          disabled={loading}
          className="flex-1 px-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading}
          className="px-5 py-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-sm flex items-center gap-2 shadow-md transition-all disabled:opacity-50 disabled:shadow-none hover:shadow-indigo-200"
        >
          <span>Send</span>
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
