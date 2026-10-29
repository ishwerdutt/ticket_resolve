"use client";

import React, { useState, useEffect } from "react";
import { MessageSquare, Ticket as TicketIcon, ShieldCheck, UserCheck, ChevronDown } from "lucide-react";
import ChatPortal from "@/components/ChatPortal";
import CustomerTickets from "@/components/CustomerTickets";
import AdminPortal from "@/components/AdminPortal";
import { DEMO_USERS, DemoUser } from "@/lib/constants";
import { loginCustomer, loginStaff } from "@/lib/api";

export default function Home() {
  const [currentUser, setCurrentUser] = useState<DemoUser>(DEMO_USERS[0]);
  const [token, setToken] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "tickets" | "admin">("chat");

  // Automatically authenticate when changing selected demo user
  useEffect(() => {
    let isMounted = true;
    async function auth() {
      setAuthLoading(true);
      try {
        let res;
        if (currentUser.role === "customer") {
          res = await loginCustomer(currentUser.email);
        } else {
          res = await loginStaff(currentUser.email);
        }
        if (isMounted) setToken(res.access_token);
      } catch (e) {
        console.error("Auth error:", e);
      } finally {
        if (isMounted) setAuthLoading(false);
      }
    }
    auth();
    return () => {
      isMounted = false;
    };
  }, [currentUser]);

  // If user switches to a staff account, default view to admin dashboard
  const handleUserSelect = (user: DemoUser) => {
    setCurrentUser(user);
    if (user.role !== "customer") {
      setActiveView("admin");
    } else if (activeView === "admin") {
      setActiveView("chat");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-100 to-slate-200 text-slate-900 flex flex-col font-sans">
      {/* Top Navigation */}
      <header className="bg-white border-b border-slate-200/80 sticky top-0 z-50 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Brand */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-700 flex items-center justify-center text-white text-xl shadow-md">
              🧵
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-indigo-700 to-violet-800 bg-clip-text text-transparent">
                  ThreadNest
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-700 border border-indigo-200">
                  AI Support v1
                </span>
              </div>
              <p className="text-xs text-slate-500 hidden sm:block">
                Autonomous e-commerce resolutions with human approval guardrails
              </p>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200/80">
            <button
              onClick={() => {
                if (currentUser.role !== "customer") {
                  setCurrentUser(DEMO_USERS[0]);
                }
                setActiveView("chat");
              }}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                activeView === "chat"
                  ? "bg-white text-indigo-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              Chat Assistant
            </button>

            {currentUser.role === "customer" && (
              <button
                onClick={() => setActiveView("tickets")}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                  activeView === "tickets"
                    ? "bg-white text-indigo-700 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <TicketIcon className="w-3.5 h-3.5" />
                My Tickets
              </button>
            )}

            <button
              onClick={() => {
                if (currentUser.role === "customer") {
                  const staffUser = DEMO_USERS.find((u) => u.role === "reviewer") || DEMO_USERS[3];
                  setCurrentUser(staffUser);
                }
                setActiveView("admin");
              }}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                activeView === "admin"
                  ? "bg-white text-indigo-700 shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              Staff Dashboard
            </button>
          </nav>

          {/* Account Switcher */}
          <div className="relative group">
            <div className="flex items-center gap-2 pl-3 pr-2 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 cursor-pointer transition-all">
              <span className="text-base">{currentUser.avatar}</span>
              <div className="text-left hidden md:block">
                <div className="text-xs font-bold text-slate-800 leading-tight">
                  {currentUser.name}
                </div>
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                  {currentUser.role}
                </div>
              </div>
              <ChevronDown className="w-3.5 h-3.5 text-slate-400 ml-1" />
            </div>

            {/* Dropdown Menu */}
            <div className="absolute right-0 mt-2 w-72 bg-white rounded-2xl shadow-xl border border-slate-200 py-2 hidden group-hover:block transition-all z-50">
              <div className="px-4 py-2 border-b border-slate-100 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Select Persona to Pair Program / Test:
              </div>
              {DEMO_USERS.map((user) => (
                <button
                  key={user.id}
                  onClick={() => handleUserSelect(user)}
                  className={`w-full px-4 py-2.5 text-left flex items-start gap-3 hover:bg-indigo-50/70 transition-colors ${
                    currentUser.id === user.id ? "bg-indigo-50/50" : ""
                  }`}
                >
                  <span className="text-xl mt-0.5">{user.avatar}</span>
                  <div className="flex-1">
                    <div className="text-xs font-bold text-slate-900 flex items-center justify-between">
                      <span>{user.name}</span>
                      {currentUser.id === user.id && (
                        <UserCheck className="w-3.5 h-3.5 text-indigo-600" />
                      )}
                    </div>
                    <div className="text-[11px] text-slate-500">{user.tag}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-5xl mx-auto w-full px-4 py-8 flex-1 flex flex-col justify-center">
        {authLoading || !token ? (
          <div className="bg-white rounded-2xl p-12 text-center shadow-lg border border-slate-200">
            <div className="w-12 h-12 rounded-full border-4 border-indigo-600 border-t-transparent animate-spin mx-auto mb-4"></div>
            <h3 className="font-bold text-slate-800 text-base">Authenticating as {currentUser.name}...</h3>
            <p className="text-xs text-slate-500 mt-1">Acquiring JWT session token from backend API</p>
          </div>
        ) : activeView === "chat" ? (
          <ChatPortal token={token} userName={currentUser.name} />
        ) : activeView === "tickets" ? (
          <CustomerTickets token={token} />
        ) : (
          <AdminPortal token={token} userName={currentUser.name} userRole={currentUser.role} />
        )}
      </main>

      {/* Footer */}
      <footer className="text-center py-4 text-xs text-slate-500 border-t border-slate-200/60 bg-white/50 backdrop-blur-xs">
        ThreadNest AI Support System · Built with Next.js, LangGraph, pgvector, and FastAPI.
      </footer>
    </div>
  );
}
