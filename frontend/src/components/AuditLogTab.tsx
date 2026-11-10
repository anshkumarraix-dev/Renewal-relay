import React, { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import type { RecoveryOpportunity } from '../types/recovery';

interface AuditLogTabProps {
  opportunities: RecoveryOpportunity[];
  loading: boolean;
  onRefresh: () => void;
  onReconcile: (opId: string) => Promise<void>;
}

export const AuditLogTab: React.FC<AuditLogTabProps> = ({
  opportunities,
  loading,
  onRefresh,
  onReconcile,
}) => {
  const [reconcilingId, setReconcilingId] = useState<string | null>(null);

  // Extract operations from opportunities
  const operations = opportunities
    .filter((opp) => opp.latest_operation)
    .map((opp) => ({
      ...opp.latest_operation!,
      subscriberName: opp.subscriber_name,
    }));

  const handleReconcileClick = async (opId: string) => {
    setReconcilingId(opId);
    try {
      await onReconcile(opId);
    } finally {
      setReconcilingId(null);
    }
  };

  return (
    <div className="tab-pane audit-pane">
      <div className="pane-header">
        <div>
          <h2>Immutable Audit Ledger & Reconciliation</h2>
          <p className="pane-subtitle">
            Cryptographic idempotency keys, PayPal Debug IDs, and authoritative reconciliation controls
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
                <th>Operation Type</th>
                <th>Subscription</th>
                <th>Idempotency Key (PayPal-Request-Id)</th>
                <th>PayPal Debug / Capture ID</th>
                <th>Amount</th>
                <th>Status</th>
                <th className="text-right">Action / Reconciliation</th>
              </tr>
            </thead>
            <tbody>
              {operations.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-muted">
                    No capture operations executed yet. Authorize a recovery in the Recovery Queue to generate an audit log entry.
                  </td>
                </tr>
              ) : (
                operations.map((op) => (
                  <tr key={op.id} className="table-row-hover">
                    <td>
                      <span className="badge badge-indigo font-mono">{op.operation_type}</span>
                    </td>
                    <td>
                      <div className="sub-name-cell">
                        <strong className="font-mono text-sm">{op.subscription_id}</strong>
                        <span className="sub-id-hint">{op.subscriberName || 'Subscriber'}</span>
                      </div>
                    </td>
                    <td>
                      <span className="font-mono text-xs text-slate-400" title={op.request_id}>
                        {op.request_id.slice(0, 18)}...
                      </span>
                    </td>
                    <td>
                      <div className="debug-id-cell">
                        {op.paypal_capture_id && (
                          <span className="font-mono text-xs text-emerald" title="PayPal Capture ID">
                            Cap: {op.paypal_capture_id}
                          </span>
                        )}
                        {op.paypal_debug_id && (
                          <span className="font-mono text-xs text-slate-400" title="PayPal Debug ID">
                            Dbg: {op.paypal_debug_id}
                          </span>
                        )}
                        {!op.paypal_capture_id && !op.paypal_debug_id && (
                          <span className="text-muted text-xs">—</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <strong className="text-white">${op.amount.toFixed(2)}</strong> {op.currency}
                    </td>
                    <td>
                      {op.status === 'COMPLETED' ? (
                        <span className="badge badge-emerald">✓ Completed</span>
                      ) : op.status === 'AMBIGUOUS' ? (
                        <span className="badge badge-amber">⚠ Ambiguous</span>
                      ) : (
                        <span className="badge badge-rose">Failed</span>
                      )}
                    </td>
                    <td className="text-right">
                      {op.status === 'AMBIGUOUS' ? (
                        <button
                          className="btn btn-warning btn-sm"
                          onClick={() => handleReconcileClick(op.id)}
                          disabled={reconcilingId === op.id}
                        >
                          <RefreshCw size={12} className={reconcilingId === op.id ? 'spin' : ''} />
                          {reconcilingId === op.id ? 'Reconciling...' : 'Reconcile with PayPal'}
                        </button>
                      ) : (
                        <span className="text-xs text-slate-500 font-mono">
                          Reconciled: {op.reconciled ? 'Yes' : 'No'}
                        </span>
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
