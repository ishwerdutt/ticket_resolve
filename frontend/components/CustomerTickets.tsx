"use client";

import React, { useState, useEffect } from "react";
import { Ticket as TicketIcon, Clock, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";
import { fetchCustomerTickets, Ticket } from "@/lib/api";

interface CustomerTicketsProps {
  token: string;
}

export default function CustomerTickets({ token }: CustomerTicketsProps) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCustomerTickets(token);
      setTickets(data);
    } catch (err: any) {
      setError(err.message || "Failed to load tickets");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTickets();
  }, [token]);

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 border border-red-200">Urgent</span>;
      case "high":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 border border-orange-200">High</span>;
      case "medium":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 border border-blue-200">Medium</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800 border border-slate-200">Low</span>;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "open":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
            <Clock className="w-3 h-3" /> Open
          </span>
        );
      case "in_progress":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800 border border-indigo-200">
            <RefreshCw className="w-3 h-3 animate-spin" /> In Progress
          </span>
        );
      case "resolved":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Resolved
          </span>
        );
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600">{status}</span>;
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
      <div className="flex items-center justify-between px-6 py-5 border-b border-slate-200 bg-slate-50/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold">
            <TicketIcon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">My Support Tickets</h2>
            <p className="text-xs text-slate-500">Track issues escalated to ThreadNest customer care staff</p>
          </div>
        </div>
        <button
          onClick={loadTickets}
          disabled={loading}
          className="p-2 text-slate-600 hover:text-indigo-600 hover:bg-slate-100 rounded-lg transition-colors"
          title="Refresh tickets"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="p-6">
        {loading ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-500" />
            Loading your support tickets...
          </div>
        ) : error ? (
          <div className="p-4 bg-red-50 text-red-700 rounded-xl text-sm border border-red-200 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        ) : tickets.length === 0 ? (
          <div className="py-12 text-center text-slate-400">
            <TicketIcon className="w-10 h-10 mx-auto text-slate-300 mb-3" />
            <p className="text-sm font-medium text-slate-700">No open tickets</p>
            <p className="text-xs text-slate-400 mt-1">If an issue needs human assistance, Tara can open a ticket for you anytime!</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tickets.map((t) => (
              <div
                key={t.id}
                className="p-4 rounded-xl border border-slate-200/90 hover:border-indigo-300 transition-all bg-white hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="font-mono text-xs text-slate-400 font-semibold">
                        #{t.id.slice(0, 8)}
                      </span>
                      {getStatusBadge(t.status)}
                      {getPriorityBadge(t.priority)}
                    </div>
                    <p className="text-sm font-medium text-slate-900 leading-snug">{t.summary}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="text-xs text-slate-400">
                      {new Date(t.created_at).toLocaleDateString("en-IN", {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
