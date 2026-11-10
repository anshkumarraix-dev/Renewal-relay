import React from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  BarChart,
  Bar,
  Legend,
} from 'recharts';
import { DollarSign, AlertOctagon, TrendingUp, Users, CheckCircle2, RefreshCw } from 'lucide-react';
import type { OverviewMetrics, RevenueMetrics, FailureMetrics, RecoveryMetrics } from '../types/analytics';

interface OverviewTabProps {
  overview: OverviewMetrics | null;
  revenue: RevenueMetrics | null;
  failures: FailureMetrics | null;
  recovery: RecoveryMetrics | null;
  loading: boolean;
  onRefresh: () => void;
}

export const OverviewTab: React.FC<OverviewTabProps> = ({
  overview,
  revenue,
  failures,
  recovery,
  loading,
  onRefresh,
}) => {
  return (
    <div className="tab-pane overview-pane">
      {/* Top Metric Cards */}
      <div className="metrics-grid">
        <div className="metric-card highlight-card">
          <div className="metric-icon-box bg-emerald">
            <DollarSign size={22} className="text-white" />
          </div>
          <div className="metric-content">
            <span className="metric-label">Verified Recovered Revenue</span>
            <div className="metric-value-row">
              <span className="metric-value">
                ${overview?.verified_recovered_revenue.toFixed(2) || '0.00'}
              </span>
              <span className="metric-currency">{overview?.currency || 'USD'}</span>
            </div>
            <span className="metric-hint text-emerald">
              <CheckCircle2 size={13} className="inline-icon" /> 100% verified via PayPal capture
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box bg-amber">
            <TrendingUp size={22} className="text-white" />
          </div>
          <div className="metric-content">
            <span className="metric-label">Outstanding Eligible Revenue</span>
            <div className="metric-value-row">
              <span className="metric-value">
                ${overview?.outstanding_eligible_revenue.toFixed(2) || '0.00'}
              </span>
              <span className="metric-currency">{overview?.currency || 'USD'}</span>
            </div>
            <span className="metric-hint">
              {overview?.eligible_recovery_opportunities || 0} eligible capture opportunities
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box bg-rose">
            <AlertOctagon size={22} className="text-white" />
          </div>
          <div className="metric-content">
            <span className="metric-label">Suspended Subscriptions</span>
            <div className="metric-value-row">
              <span className="metric-value">{overview?.suspended_subscriptions || 0}</span>
              <span className="metric-unit">of {overview?.total_subscriptions || 0}</span>
            </div>
            <span className="metric-hint text-rose">
              At risk of permanent involuntary churn
            </span>
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-icon-box bg-blue">
            <Users size={22} className="text-white" />
          </div>
          <div className="metric-content">
            <span className="metric-label">Active Subscriptions</span>
            <div className="metric-value-row">
              <span className="metric-value">{overview?.active_subscriptions || 0}</span>
              <span className="metric-unit">healthy</span>
            </div>
            <span className="metric-hint">
              Recovery success rate: {recovery?.success_rate_percentage || 0}%
            </span>
          </div>
        </div>
      </div>

      {/* Chart Section */}
      <div className="charts-grid">
        <div className="card chart-card">
          <div className="card-header">
            <div>
              <h3>Revenue Recovery Velocity</h3>
              <p className="card-subtitle">Potential recoverable vs. verified completed PayPal revenue</p>
            </div>
            <button className="btn-icon-subtle" onClick={onRefresh} disabled={loading} title="Refresh">
              <RefreshCw size={14} className={loading ? 'spin' : ''} />
            </button>
          </div>
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={revenue?.revenue_by_month || []}>
                <defs>
                  <linearGradient id="colorRecovered" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="colorPotential" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis dataKey="month" stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', borderRadius: '8px' }}
                  formatter={(val: unknown) => typeof val === 'number' ? [`$${val.toFixed(2)}`, ''] : [String(val), '']}
                />
                <Legend />
                <Area
                  type="monotone"
                  dataKey="potential"
                  name="At-Risk Potential ($)"
                  stroke="#6366f1"
                  fillOpacity={1}
                  fill="url(#colorPotential)"
                />
                <Area
                  type="monotone"
                  dataKey="recovered"
                  name="Verified Recovered ($)"
                  stroke="#10b981"
                  fillOpacity={1}
                  fill="url(#colorRecovered)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card chart-card">
          <div className="card-header">
            <div>
              <h3>Decline Reason Distribution</h3>
              <p className="card-subtitle">AI-classified failure categories across merchant portfolio</p>
            </div>
          </div>
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={failures?.categories || []} layout="vertical" margin={{ left: 30, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.5} />
                <XAxis type="number" stroke="#94a3b8" />
                <YAxis dataKey="category" type="category" stroke="#94a3b8" width={110} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', borderColor: '#475569', borderRadius: '8px' }}
                  formatter={(val: unknown) => typeof val === 'number' ? [`${val} occurrences`, 'Count'] : [String(val), 'Count']}
                />
                <Bar dataKey="count" name="Failure Count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
