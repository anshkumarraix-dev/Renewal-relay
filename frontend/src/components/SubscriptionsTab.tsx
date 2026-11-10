import React from 'react';
import { RefreshCw, CheckCircle2, AlertOctagon, XCircle, Clock } from 'lucide-react';
import type { SubscriptionItem } from '../types/recovery';

interface SubscriptionsTabProps {
  subscriptions: SubscriptionItem[];
  loading: boolean;
  onRefresh: () => void;
}

export const SubscriptionsTab: React.FC<SubscriptionsTabProps> = ({
  subscriptions,
  loading,
  onRefresh,
}) => {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return <span className="badge badge-emerald"><CheckCircle2 size={12} className="inline-icon" /> Active</span>;
      case 'SUSPENDED':
        return <span className="badge badge-rose"><AlertOctagon size={12} className="inline-icon" /> Suspended</span>;
      case 'CANCELLED':
        return <span className="badge badge-muted"><XCircle size={12} className="inline-icon" /> Cancelled</span>;
      default:
        return <span className="badge badge-blue">{status}</span>;
    }
  };

  const formatDate = (dtStr?: string) => {
    if (!dtStr) return '—';
    try {
      return new Date(dtStr).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    } catch {
      return dtStr;
    }
  };

  return (
    <div className="tab-pane subscriptions-pane">
      <div className="pane-header">
        <div>
          <h2>PayPal Subscriptions Monitor</h2>
          <p className="pane-subtitle">
            Synchronized subscription lifecycle states, billing schedules, and failure telemetry
          </p>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Refresh
        </button>
      </div>

      <div className="card table-card">
        <div className="table-responsive">
          <table className="data-table">
            <thead>
              <tr>
                <th>Subscription ID</th>
                <th>Subscriber</th>
                <th>Status</th>
                <th>Outstanding Balance</th>
                <th>Failed Count</th>
                <th>Next Scheduled Billing</th>
                <th>Last Payment</th>
              </tr>
            </thead>
            <tbody>
              {subscriptions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-muted">
                    No subscriptions tracked yet. Click "Seed Sandbox Demo" to populate test data.
                  </td>
                </tr>
              ) : (
                subscriptions.map((sub) => (
                  <tr key={sub.id} className="table-row-hover">
                    <td className="font-mono text-sm font-semibold text-sky-400">
                      {sub.id}
                    </td>
                    <td>
                      <div className="sub-name-cell">
                        <strong>{sub.subscriber_name || 'Subscriber'}</strong>
                        <span className="sub-id-hint">{sub.subscriber_email || '—'}</span>
                      </div>
                    </td>
                    <td>{getStatusBadge(sub.status)}</td>
                    <td>
                      <div className="amount-cell">
                        <strong className={sub.outstanding_balance_amount > 0 ? 'text-amber' : 'text-slate-300'}>
                          ${sub.outstanding_balance_amount.toFixed(2)}
                        </strong>
                        <span className="currency-hint">{sub.currency}</span>
                      </div>
                    </td>
                    <td>
                      {sub.failed_payment_count > 0 ? (
                        <span className="badge badge-amber">{sub.failed_payment_count} failed</span>
                      ) : (
                        <span className="text-emerald text-xs">0 failures</span>
                      )}
                    </td>
                    <td>
                      <span className="date-cell">
                        <Clock size={12} className="inline-icon text-muted" />
                        {formatDate(sub.next_billing_time)}
                      </span>
                    </td>
                    <td>
                      <span className="date-cell">
                        {sub.last_payment_amount ? `$${sub.last_payment_amount.toFixed(2)} on ` : ''}
                        {formatDate(sub.last_payment_time)}
                      </span>
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
