"use client";

import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  Check,
  X,
  AlertCircle,
  Clock,
  Ticket as TicketIcon,
  BarChart3,
  RefreshCw,
  TrendingUp,
  DollarSign,
  FileCheck2,
} from "lucide-react";
import {
  fetchApprovals,
  decideApproval,
  fetchAllTickets,
  fetchMetrics,
  Approval,
  Ticket,
  Metrics,
} from "@/lib/api";

interface AdminPortalProps {
  token: string;
  userName: string;
  userRole: string;
}

export default function AdminPortal({ token, userName, userRole }: AdminPortalProps) {
  const [activeTab, setActiveTab] = useState<"approvals" | "tickets" | "metrics">("approvals");

  // State
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const loadData = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      const [apprData, tickData, metrData] = await Promise.all([
        fetchApprovals(token).catch(() => []),
        fetchAllTickets(token).catch(() => []),
        fetchMetrics(token).catch(() => null),
      ]);
      setApprovals(apprData);
      setTickets(tickData);
      setMetrics(metrData);
    } catch (err: any) {
      setFeedback({ type: "error", msg: err.message || "Failed to load dashboard data" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token]);

  const handleDecision = async (approvalId: string, action: "approve" | "reject") => {
    setActionLoading(approvalId);
    setFeedback(null);
    try {
      await decideApproval(
        approvalId,
        action,
        token,
        action === "approve" ? "Approved by staff reviewer." : "Policy requirement not met."
      );
      setFeedback({
        type: "success",
        msg: `Successfully ${action === "approve" ? "approved" : "rejected"} request #${approvalId.slice(0, 8)}`,
      });
      await loadData();
    } catch (err: any) {
      setFeedback({ type: "error", msg: err.message || "Decision submission failed" });
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between px-6 py-5 border-b border-slate-200 bg-slate-900 text-white gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/20 text-violet-300 border border-violet-400/30 flex items-center justify-center font-bold">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold">ThreadNest Staff Portal</h2>
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-violet-600 text-white uppercase tracking-wider">
                {userRole}
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Logged in as {userName} · Human-in-the-Loop Queue & Policy Auditing
            </p>
          </div>
        </div>

        {/* Tab Buttons */}
        <div className="flex items-center gap-1.5 bg-slate-800 p-1.5 rounded-xl border border-slate-700">
          <button
            onClick={() => setActiveTab("approvals")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "approvals"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-300 hover:text-white hover:bg-slate-700/50"
            }`}
          >
            <Clock className="w-3.5 h-3.5" />
            Approvals
            {approvals.filter((a) => a.status === "pending").length > 0 && (
              <span className="ml-1 px-1.5 py-0.2 bg-amber-400 text-slate-900 text-[10px] font-black rounded-full">
                {approvals.filter((a) => a.status === "pending").length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("tickets")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "tickets"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-300 hover:text-white hover:bg-slate-700/50"
            }`}
          >
            <TicketIcon className="w-3.5 h-3.5" />
            All Tickets ({tickets.length})
          </button>
          <button
            onClick={() => setActiveTab("metrics")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
              activeTab === "metrics"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-300 hover:text-white hover:bg-slate-700/50"
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Store Metrics
          </button>
          <button
            onClick={loadData}
            title="Refresh"
            disabled={loading}
            className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors ml-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {/* Notifications */}
      {feedback && (
        <div
          className={`px-6 py-3 text-xs font-medium border-b flex items-center gap-2 ${
            feedback.type === "success"
              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
              : "bg-red-50 text-red-800 border-red-200"
          }`}
        >
          {feedback.type === "success" ? <Check className="w-4 h-4 text-emerald-600" /> : <AlertCircle className="w-4 h-4 text-red-600" />}
          {feedback.msg}
        </div>
      )}

      {/* Content Area */}
      <div className="p-6">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
            Loading portal data...
          </div>
        ) : activeTab === "approvals" ? (
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-bold text-slate-900 text-base">Human Approval Queue</h3>
                <p className="text-xs text-slate-500">
                  Actions exceeding autonomous policy limits (e.g., refunds &gt; ₹1,000 INR or product replacements)
                </p>
              </div>
            </div>

            {approvals.length === 0 ? (
              <div className="py-16 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                <FileCheck2 className="w-10 h-10 mx-auto text-slate-300 mb-2" />
                <p className="text-sm font-semibold text-slate-700">Approval queue is clear!</p>
                <p className="text-xs text-slate-400 mt-0.5">When Tara flags a high-value refund or replacement, it will appear here for one-click verification.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {approvals.map((appr) => {
                  const isPending = appr.status === "pending";
                  return (
                    <div
                      key={appr.id}
                      className={`p-5 rounded-xl border transition-all ${
                        isPending
                          ? "bg-amber-50/40 border-amber-200 shadow-sm"
                          : "bg-white border-slate-200 opacity-75"
                      }`}
                    >
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="space-y-1.5 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-slate-400 font-bold">
                              #{appr.id.slice(0, 8)}
                            </span>
                            <span
                              className={`px-2 py-0.5 text-xs font-bold uppercase rounded-md ${
                                appr.action === "create_refund"
                                  ? "bg-rose-100 text-rose-800"
                                  : "bg-blue-100 text-blue-800"
                              }`}
                            >
                              {appr.action.replace("_", " ")}
                            </span>
                            <span
                              className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                                isPending
                                  ? "bg-amber-100 text-amber-800 border border-amber-300"
                                  : appr.status === "approved"
                                  ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                                  : "bg-red-100 text-red-800 border border-red-300"
                              }`}
                            >
                              {appr.status.toUpperCase()}
                            </span>
                          </div>

                          <div className="text-sm font-semibold text-slate-900">
                            {appr.args_json?.amount ? (
                              <span className="text-rose-600 font-bold mr-2">
                                Amount: ₹{Number(appr.args_json.amount).toFixed(2)} INR
                              </span>
                            ) : null}
                            <span className="text-slate-600">
                              Order ID: <span className="font-mono">{appr.args_json?.order_id?.slice(0, 8) || "N/A"}</span>
                            </span>
                          </div>

                          {appr.reasoning && (
                            <p className="text-xs text-slate-600 bg-white/70 p-2.5 rounded-lg border border-slate-200/80 leading-relaxed">
                              💡 <span className="font-medium text-slate-700">Agent Reasoning:</span> {appr.reasoning}
                            </p>
                          )}
                        </div>

                        {/* Actions */}
                        {isPending && (
                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              onClick={() => handleDecision(appr.id, "reject")}
                              disabled={actionLoading === appr.id}
                              className="px-3.5 py-2 rounded-xl text-xs font-semibold border border-red-200 text-red-700 hover:bg-red-50 transition-colors flex items-center gap-1.5 disabled:opacity-50"
                            >
                              <X className="w-3.5 h-3.5" /> Reject
                            </button>
                            <button
                              onClick={() => handleDecision(appr.id, "approve")}
                              disabled={actionLoading === appr.id}
                              className="px-4 py-2 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
                            >
                              <Check className="w-3.5 h-3.5" /> Approve Action
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : activeTab === "tickets" ? (
          <div>
            <div className="mb-4">
              <h3 className="font-bold text-slate-900 text-base">Store Ticket Center</h3>
              <p className="text-xs text-slate-500">Live ticket queue across all ThreadNest customers</p>
            </div>

            <div className="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden bg-white">
              {tickets.map((t) => (
                <div key={t.id} className="p-4 hover:bg-slate-50 transition-colors flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-slate-400 font-bold">#{t.id.slice(0, 8)}</span>
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700">
                        {t.status}
                      </span>
                      <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                        t.priority === "urgent" ? "bg-red-100 text-red-800" :
                        t.priority === "high" ? "bg-orange-100 text-orange-800" : "bg-blue-100 text-blue-800"
                      }`}>
                        {t.priority}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-slate-900">{t.summary}</p>
                    <p className="text-xs text-slate-400">Customer ID: {t.customer_id}</p>
                  </div>
                  <span className="text-xs text-slate-400 shrink-0">
                    {new Date(t.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div>
            <div className="mb-6">
              <h3 className="font-bold text-slate-900 text-base">Store Resolution & Observability</h3>
              <p className="text-xs text-slate-500">Real-time metrics calculated across all customer interactions</p>
            </div>

            {metrics && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                <div className="p-5 rounded-2xl bg-indigo-50/60 border border-indigo-100">
                  <div className="flex items-center justify-between text-indigo-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Total Conversations</span>
                    <TrendingUp className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">{metrics.total_conversations}</div>
                  <p className="text-xs text-slate-500 mt-1">Sessions handled by Tara</p>
                </div>

                <div className="p-5 rounded-2xl bg-emerald-50/60 border border-emerald-100">
                  <div className="flex items-center justify-between text-emerald-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Auto-Resolved</span>
                    <Check className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">{metrics.resolved_count}</div>
                  <p className="text-xs text-slate-500 mt-1">Closed without human intervention</p>
                </div>

                <div className="p-5 rounded-2xl bg-rose-50/60 border border-rose-100">
                  <div className="flex items-center justify-between text-rose-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Escalated</span>
                    <AlertCircle className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">{metrics.escalated_count}</div>
                  <p className="text-xs text-slate-500 mt-1">Routed to human staff</p>
                </div>

                <div className="p-5 rounded-2xl bg-amber-50/60 border border-amber-100">
                  <div className="flex items-center justify-between text-amber-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Pending Approvals</span>
                    <Clock className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">{metrics.pending_approvals_count}</div>
                  <p className="text-xs text-slate-500 mt-1">Awaiting reviewer decision</p>
                </div>

                <div className="p-5 rounded-2xl bg-violet-50/60 border border-violet-100">
                  <div className="flex items-center justify-between text-violet-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Total Refunded</span>
                    <DollarSign className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">₹{metrics.total_refunds_amount.toFixed(2)}</div>
                  <p className="text-xs text-slate-500 mt-1">Approved INR refund volume</p>
                </div>

                <div className="p-5 rounded-2xl bg-slate-50 border border-slate-200">
                  <div className="flex items-center justify-between text-slate-700 mb-2">
                    <span className="text-xs font-semibold uppercase">Avg Tool Calls</span>
                    <BarChart3 className="w-4 h-4" />
                  </div>
                  <div className="text-3xl font-extrabold text-slate-900">{metrics.avg_tool_calls_per_conversation.toFixed(1)}</div>
                  <p className="text-xs text-slate-500 mt-1">Actions per conversation</p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
