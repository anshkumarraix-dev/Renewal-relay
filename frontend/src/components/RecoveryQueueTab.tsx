import React, { useState } from 'react';
import { CheckCircle2, RefreshCw, ArrowUpRight } from 'lucide-react';
import type { RecoveryOpportunity } from '../types/recovery';

interface RecoveryQueueTabProps {
  opportunities: RecoveryOpportunity[];
  loading: boolean;
  onRefresh: () => void;
  onSelectOpportunity: (opp: RecoveryOpportunity) => void;
}

export const RecoveryQueueTab: React.FC<RecoveryQueueTabProps> = ({
  opportunities,
  loading,
  onRefresh,
  onSelectOpportunity,
}) => {
  const [filter, setFilter] = useState<string>('ALL');

  const filteredOpps = opportunities.filter((opp) => {
    if (filter === 'ALL') return true;
    if (filter === 'ELIGIBLE') return opp.status === 'ELIGIBLE' || opp.status === 'IDENTIFIED';
    if (filter === 'RECOVERED') return opp.status === 'RECOVERED';
    if (filter === 'AMBIGUOUS') return opp.status === 'AMBIGUOUS_RECONCILING';
    return true;
  });

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'RECOVERED':
        return <span className="badge badge-emerald">✓ Recovered</span>;
      case 'ELIGIBLE':
        return <span className="badge badge-indigo">⚡ Eligible</span>;
      case 'AMBIGUOUS_RECONCILING':
        return <span className="badge badge-amber">⚠ Ambiguous (Needs Reconcile)</span>;
      case 'REJECTED':
        return <span className="badge badge-muted">Dismissed</span>;
      default:
        return <span className="badge badge-blue">{status}</span>;
    }
  };

  return (
    <div className="tab-pane queue-pane">
      <div className="pane-header">
        <div>
          <h2>Merchant Recovery Queue</h2>
          <p className="pane-subtitle">
            Deterministic eligibility evaluation paired with advisory AI insights for merchant authorization
          </p>
        </div>
        <div className="pane-actions">
          <div className="filter-pill-group">
            <button
              className={`pill-btn ${filter === 'ALL' ? 'active' : ''}`}
              onClick={() => setFilter('ALL')}
            >
              All ({opportunities.length})
            </button>
            <button
              className={`pill-btn ${filter === 'ELIGIBLE' ? 'active' : ''}`}
              onClick={() => setFilter('ELIGIBLE')}
            >
              Eligible ({opportunities.filter((o) => o.status === 'ELIGIBLE' || o.status === 'IDENTIFIED').length})
            </button>
            <button
              className={`pill-btn ${filter === 'RECOVERED' ? 'active' : ''}`}
              onClick={() => setFilter('RECOVERED')}
            >
              Recovered ({opportunities.filter((o) => o.status === 'RECOVERED').length})
            </button>
            <button
              className={`pill-btn ${filter === 'AMBIGUOUS' ? 'active' : ''}`}
              onClick={() => setFilter('AMBIGUOUS')}
            >
              Ambiguous ({opportunities.filter((o) => o.status === 'AMBIGUOUS_RECONCILING').length})
            </button>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="card table-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Subscriber & ID</th>
                <th>Outstanding Balance</th>
                <th>Failed Count</th>
                <th>Deterministic Decision</th>
                <th>AI Advisory Classification</th>
                <th>Recovery Status</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredOpps.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-muted">
                    No recovery opportunities found matching the selected filter.
                  </td>
                </tr>
              ) : (
                filteredOpps.map((opp) => (
                  <tr key={opp.id} className="table-row-hover">
                    <td>
                      <div className="sub-name-cell">
                        <strong>{opp.subscriber_name || 'Subscriber'}</strong>
                        <span className="sub-id-hint font-mono">{opp.subscription_id}</span>
                      </div>
                    </td>
                    <td>
                      <div className="amount-cell">
                        <strong className="text-white">${opp.eligible_amount.toFixed(2)}</strong>
                        <span className="currency-hint">{opp.currency}</span>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-amber">{opp.failed_payment_count} failed</span>
                    </td>
                    <td>
                      <div className="policy-cell">
                        <span className="decision-tag font-semibold text-emerald">
                          {opp.latest_evaluation?.decision || 'ELIGIBLE'}
                        </span>
                        <span className="policy-reason-hint" title={opp.latest_evaluation?.reason}>
                          {opp.latest_evaluation?.reason?.slice(0, 42)}...
                        </span>
                      </div>
                    </td>
                    <td>
                      {opp.latest_ai_recommendation ? (
                        <div className="ai-cell">
                          <span className="ai-category-pill">
                            {opp.latest_ai_recommendation.failure_category.replace('_', ' ')}
                          </span>
                          <span className="ai-conf-hint">
                            {Math.round(opp.latest_ai_recommendation.confidence_score * 100)}% conf
                          </span>
                        </div>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td>{getStatusBadge(opp.status)}</td>
                    <td className="text-right">
                      {opp.status === 'RECOVERED' ? (
                        <span className="text-emerald text-sm font-semibold">
                          <CheckCircle2 size={14} className="inline-icon" /> Captured
                        </span>
                      ) : (
                        <button
                          className="btn btn-primary btn-sm"
                          onClick={() => onSelectOpportunity(opp)}
                        >
                          Review & Authorize
                          <ArrowUpRight size={13} className="btn-icon-right" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
