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
  Activity,
  Zap,
  Terminal,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  Filter,
} from "lucide-react";
import {
  fetchApprovals,
  decideApproval,
  fetchAllTickets,
  fetchMetrics,
  fetchActivity,
  Approval,
  Ticket,
  Metrics,
  ActivityEvent,
} from "@/lib/api";

interface AdminPortalProps {
  token: string;
  userName: string;
  userRole: string;
}

export default function AdminPortal({ token, userName, userRole }: AdminPortalProps) {
  const [activeTab, setActiveTab] = useState<"activity" | "approvals" | "tickets" | "metrics">("activity");

  // State
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  const [loading, setLoading] = useState(true);
  const [liveMode, setLiveMode] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  // Filters & Expanded State for Activity Stream
  const [activityFilter, setActivityFilter] = useState<"all" | "tool_call" | "approval" | "ticket" | "message">("all");
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});

  const toggleEventExpand = (id: string) => {
    setExpandedEvents((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const loadData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [apprData, tickData, metrData, actData] = await Promise.all([
        fetchApprovals(token).catch(() => []),
        fetchAllTickets(token).catch(() => []),
        fetchMetrics(token).catch(() => null),
        fetchActivity(token, 40).catch(() => []),
      ]);
      setApprovals(apprData);
      setTickets(tickData);
      setMetrics(metrData);
      setActivity(actData);
      setLastRefreshed(new Date());
    } catch (err: any) {
      if (!silent) {
        setFeedback({ type: "error", msg: err.message || "Failed to load dashboard data" });
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    loadData(false);
  }, [token]);

  // Real-time live polling every 2.5s
  useEffect(() => {
    if (!liveMode || !token) return;

    const interval = setInterval(() => {
      loadData(true);
    }, 2500);

    return () => clearInterval(interval);
  }, [token, liveMode]);

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
      await loadData(true);
    } catch (err: any) {
      setFeedback({ type: "error", msg: err.message || "Decision submission failed" });
    } finally {
      setActionLoading(null);
    }
  };

  const filteredActivity = activity.filter((item) => {
    if (activityFilter === "all") return true;
    return item.type === activityFilter;
  });

  const pendingApprovalsCount = approvals.filter((a) => a.status === "pending").length;

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden flex flex-col h-[740px]">
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
              Logged in as {userName} · Live Agent Telemetry & Approvals
            </p>
          </div>
        </div>

        {/* Live Indicator & Tab Buttons */}
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          {/* Live Stream Pulsing Badge */}
          <button
            onClick={() => setLiveMode(!liveMode)}
            className={`px-2.5 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2 transition-all ${
              liveMode
                ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30"
                : "bg-slate-800 text-slate-400 border border-slate-700 hover:text-white"
            }`}
            title={liveMode ? "Auto-refreshing every 2.5s. Click to pause." : "Paused. Click to resume live polling."}
          >
            <span className="relative flex h-2 w-2">
              {liveMode && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              )}
              <span className={`relative inline-flex rounded-full h-2 w-2 ${liveMode ? "bg-emerald-400" : "bg-slate-500"}`} />
            </span>
            <span>{liveMode ? "LIVE" : "PAUSED"}</span>
          </button>

          {/* Tab Navigation */}
          <div className="flex items-center gap-1 bg-slate-800 p-1 rounded-xl border border-slate-700">
            <button
              onClick={() => setActiveTab("activity")}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 ${
                activeTab === "activity"
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-300 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              Live Feed
              {activity.length > 0 && (
                <span className="ml-1 px-1.5 py-0.2 bg-indigo-900/80 text-indigo-200 text-[10px] font-bold rounded-full">
                  {activity.length}
                </span>
              )}
            </button>

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
              {pendingApprovalsCount > 0 && (
                <span className="ml-1 px-1.5 py-0.2 bg-amber-400 text-slate-900 text-[10px] font-black rounded-full animate-pulse">
                  {pendingApprovalsCount}
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
              Tickets ({tickets.length})
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
              Metrics
            </button>

            <button
              onClick={() => loadData(false)}
              title="Manual Refresh"
              disabled={loading}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors ml-0.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
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
      <div className="p-6 flex-1 overflow-y-auto">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-sm">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
            Loading portal data...
          </div>
        ) : activeTab === "activity" ? (
          /* ─── LIVE ACTIVITY FEED TAB ─── */
          <div>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-bold text-slate-900 text-base">Real-Time Agent Activity & Telemetry</h3>
                  <span className="flex items-center gap-1 text-[11px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Auto-Streaming
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Live execution trace of customer chats, GPT-4o tool executions, RAG retrieval, and approvals
                </p>
              </div>

              {/* Filter Chips */}
              <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl text-xs font-medium text-slate-600 overflow-x-auto">
                <button
                  onClick={() => setActivityFilter("all")}
                  className={`px-2.5 py-1 rounded-lg transition-all ${
                    activityFilter === "all" ? "bg-white text-indigo-600 shadow-xs font-semibold" : "hover:text-slate-900"
                  }`}
                >
                  All ({activity.length})
                </button>
                <button
                  onClick={() => setActivityFilter("tool_call")}
                  className={`px-2.5 py-1 rounded-lg transition-all flex items-center gap-1 ${
                    activityFilter === "tool_call" ? "bg-white text-indigo-600 shadow-xs font-semibold" : "hover:text-slate-900"
                  }`}
                >
                  <Terminal className="w-3 h-3 text-blue-500" />
                  Tools ({activity.filter((a) => a.type === "tool_call").length})
                </button>
                <button
                  onClick={() => setActivityFilter("approval")}
                  className={`px-2.5 py-1 rounded-lg transition-all flex items-center gap-1 ${
                    activityFilter === "approval" ? "bg-white text-indigo-600 shadow-xs font-semibold" : "hover:text-slate-900"
                  }`}
                >
                  <ShieldCheck className="w-3 h-3 text-amber-500" />
                  Approvals ({activity.filter((a) => a.type === "approval").length})
                </button>
                <button
                  onClick={() => setActivityFilter("ticket")}
                  className={`px-2.5 py-1 rounded-lg transition-all flex items-center gap-1 ${
                    activityFilter === "ticket" ? "bg-white text-indigo-600 shadow-xs font-semibold" : "hover:text-slate-900"
                  }`}
                >
                  <TicketIcon className="w-3 h-3 text-purple-500" />
                  Tickets ({activity.filter((a) => a.type === "ticket").length})
                </button>
                <button
                  onClick={() => setActivityFilter("message")}
                  className={`px-2.5 py-1 rounded-lg transition-all flex items-center gap-1 ${
                    activityFilter === "message" ? "bg-white text-indigo-600 shadow-xs font-semibold" : "hover:text-slate-900"
                  }`}
                >
                  <MessageSquare className="w-3 h-3 text-emerald-500" />
                  Chat ({activity.filter((a) => a.type === "message").length})
                </button>
              </div>
            </div>

            {/* Event List */}
            {filteredActivity.length === 0 ? (
              <div className="py-16 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                <Activity className="w-10 h-10 mx-auto text-slate-300 mb-2" />
                <p className="text-sm font-semibold text-slate-700">No events found in stream</p>
                <p className="text-xs text-slate-400 mt-0.5">Send a message in the chat widget to see live execution events.</p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {filteredActivity.map((evt) => {
                  const isExpanded = !!expandedEvents[evt.id];
                  const timeStr = new Date(evt.created_at).toLocaleTimeString();

                  return (
                    <div
                      key={evt.id}
                      className="border border-slate-200/90 rounded-xl p-3.5 hover:border-slate-300 transition-all bg-white hover:shadow-xs"
                    >
                      <div className="flex items-start justify-between gap-3">
                        {/* Left: Icon & Description */}
                        <div className="flex items-start gap-3 flex-1 min-w-0">
                          <div
                            className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                              evt.type === "tool_call"
                                ? "bg-blue-50 text-blue-600 border border-blue-200"
                                : evt.type === "approval"
                                ? "bg-amber-50 text-amber-600 border border-amber-200"
                                : evt.type === "ticket"
                                ? "bg-purple-50 text-purple-600 border border-purple-200"
                                : "bg-emerald-50 text-emerald-600 border border-emerald-200"
                            }`}
                          >
                            {evt.type === "tool_call" ? (
                              <Terminal className="w-4 h-4" />
                            ) : evt.type === "approval" ? (
                              <ShieldCheck className="w-4 h-4" />
                            ) : evt.type === "ticket" ? (
                              <TicketIcon className="w-4 h-4" />
                            ) : (
                              <MessageSquare className="w-4 h-4" />
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-bold text-slate-900">{evt.title}</span>

                              {/* Customer chip */}
                              {evt.customer_name && (
                                <span className="text-[11px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                                  {evt.customer_name}
                                </span>
                              )}

                              {/* Latency badge */}
                              {evt.latency_ms !== null && evt.latency_ms !== undefined && (
                                <span className="text-[11px] font-mono font-semibold text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 flex items-center gap-0.5">
                                  <Zap className="w-3 h-3 text-emerald-500" />
                                  {evt.latency_ms}ms
                                </span>
                              )}

                              {/* Approval or Ticket Status */}
                              {evt.status && (
                                <span
                                  className={`text-[10px] font-bold uppercase px-1.5 py-0.2 rounded ${
                                    evt.status === "pending"
                                      ? "bg-amber-100 text-amber-800"
                                      : evt.status === "approved" || evt.status === "resolved"
                                      ? "bg-emerald-100 text-emerald-800"
                                      : evt.status === "rejected" || evt.status === "urgent"
                                      ? "bg-rose-100 text-rose-800"
                                      : "bg-slate-100 text-slate-700"
                                  }`}
                                >
                                  {evt.status}
                                </span>
                              )}
                            </div>

                            <p className="text-xs text-slate-600 mt-1 line-clamp-2 leading-relaxed">
                              {evt.description}
                            </p>
                          </div>
                        </div>

                        {/* Right: Timestamp & Expand button */}
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-[11px] font-mono text-slate-400">{timeStr}</span>
                          {evt.details && (
                            <button
                              onClick={() => toggleEventExpand(evt.id)}
                              className="p-1 hover:bg-slate-100 rounded text-slate-400 hover:text-slate-700 transition-colors"
                              title="Toggle details"
                            >
                              {isExpanded ? (
                                <ChevronUp className="w-4 h-4" />
                              ) : (
                                <ChevronDown className="w-4 h-4" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Expanded Details JSON Inspector */}
                      {isExpanded && evt.details && (
                        <div className="mt-3 pt-3 border-t border-slate-100">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                              Payload Details
                            </span>
                            {evt.conversation_id && (
                              <span className="text-[10px] font-mono text-slate-400">
                                Conv ID: {evt.conversation_id}
                              </span>
                            )}
                          </div>
                          <pre className="text-[11px] font-mono bg-slate-900 text-slate-100 p-3 rounded-lg overflow-x-auto max-h-48 leading-tight">
                            {JSON.stringify(evt.details, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : activeTab === "approvals" ? (
          /* ─── APPROVALS QUEUE TAB ─── */
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
                <p className="text-xs text-slate-400 mt-0.5">
                  When Tara flags a high-value refund or replacement, it will appear here for one-click verification.
                </p>
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
          /* ─── ALL TICKETS TAB ─── */
          <div>
            <div className="mb-4">
              <h3 className="font-bold text-slate-900 text-base">Store Ticket Center</h3>
              <p className="text-xs text-slate-500">Live ticket queue across all ThreadNest customers</p>
            </div>

            <div className="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden bg-white">
              {tickets.length === 0 ? (
                <div className="p-8 text-center text-slate-400 text-xs">No tickets recorded yet.</div>
              ) : (
                tickets.map((t) => (
                  <div key={t.id} className="p-4 hover:bg-slate-50 transition-colors flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs text-slate-400 font-bold">#{t.id.slice(0, 8)}</span>
                        <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-slate-100 text-slate-700">
                          {t.status}
                        </span>
                        <span
                          className={`px-2 py-0.5 text-xs font-semibold rounded-full ${
                            t.priority === "urgent"
                              ? "bg-red-100 text-red-800"
                              : t.priority === "high"
                              ? "bg-orange-100 text-orange-800"
                              : "bg-blue-100 text-blue-800"
                          }`}
                        >
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
                ))
              )}
            </div>
          </div>
        ) : (
          /* ─── STORE METRICS TAB ─── */
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
