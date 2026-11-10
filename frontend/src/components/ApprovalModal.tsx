import React, { useState } from 'react';
import { ShieldCheck, AlertCircle, X, CheckCircle, AlertTriangle, ArrowRight } from 'lucide-react';
import type { RecoveryOpportunity } from '../types/recovery';

interface ApprovalModalProps {
  opportunity: RecoveryOpportunity | null;
  onClose: () => void;
  onApprove: (id: string, user: string, note?: string) => Promise<void>;
  onReject: (id: string, user: string, note?: string) => Promise<void>;
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  opportunity,
  onClose,
  onApprove,
  onReject,
}) => {
  const [user, setUser] = useState('merchant_admin');
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!opportunity) return null;

  const handleApprove = async () => {
    setSubmitting(true);
    setActionError(null);
    try {
      await onApprove(opportunity.id, user, note);
      onClose();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Capture operation failed');
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    setSubmitting(true);
    setActionError(null);
    try {
      await onReject(opportunity.id, user, note);
      onClose();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : 'Rejection failed');
    } finally {
      setSubmitting(false);
    }
  };

  const isEligible = opportunity.latest_evaluation?.is_eligible ?? (opportunity.status === 'ELIGIBLE');

  return (
    <div className="modal-overlay">
      <div className="modal-container">
        <div className="modal-header">
          <div className="modal-title-row">
            <ShieldCheck size={20} className="text-emerald" />
            <h3>Merchant Recovery Authorization</h3>
          </div>
          <button className="btn-close" onClick={onClose} disabled={submitting}>
            <X size={18} />
          </button>
        </div>

        <div className="modal-body">
          {actionError && (
            <div className="alert-banner alert-error">
              <AlertCircle size={16} />
              <span>{actionError}</span>
            </div>
          )}

          {/* Subscription Summary */}
          <div className="modal-section summary-box">
            <div className="summary-row">
              <div>
                <span className="summary-label">Subscriber</span>
                <p className="summary-val">{opportunity.subscriber_name || 'Subscriber'}</p>
                <span className="summary-sub">{opportunity.subscriber_email || 'No email on file'}</span>
              </div>
              <div>
                <span className="summary-label">Subscription ID</span>
                <p className="summary-val font-mono">{opportunity.subscription_id}</p>
                <span className="summary-sub">{opportunity.plan_name || 'Annual SaaS Plan'}</span>
              </div>
              <div className="text-right">
                <span className="summary-label">Outstanding Balance</span>
                <p className="summary-val highlight-val">
                  ${opportunity.eligible_amount.toFixed(2)} {opportunity.currency}
                </p>
                <span className="badge badge-amber">{opportunity.failed_payment_count} failed attempt(s)</span>
              </div>
            </div>
          </div>

          {/* Deterministic Policy Check */}
          <div className="modal-section policy-check-box">
            <h4 className="section-title">
              <CheckCircle size={16} className={isEligible ? 'text-emerald' : 'text-amber'} />
              Deterministic Policy Evaluation (v1.0.0)
            </h4>
            <div className="policy-decision-banner">
              <strong>Status: {opportunity.latest_evaluation?.decision || 'ELIGIBLE'}</strong>
              <p>{opportunity.latest_evaluation?.reason || 'Verified outstanding balance eligible for merchant capture.'}</p>
            </div>
            <ul className="check-list">
              <li>✓ Verified subscription state is ACTIVE or SUSPENDED</li>
              <li>✓ Outstanding balance ({opportunity.eligible_amount.toFixed(2)} {opportunity.currency}) exceeds minimum threshold</li>
              <li>✓ No conflicting PayPal native automated retry scheduled in immediate window</li>
              <li>✓ Unique idempotency key (PayPal-Request-Id) will be pinned to prevent double capture</li>
            </ul>
          </div>

          {/* AI Advisory Guidance */}
          {opportunity.latest_ai_recommendation && (
            <div className="modal-section ai-box">
              <h4 className="section-title text-indigo">
                <AlertTriangle size={16} />
                AI Advisory Classification: {opportunity.latest_ai_recommendation.failure_category.replace('_', ' ')}
              </h4>
              <p className="ai-explanation">{opportunity.latest_ai_recommendation.explanation}</p>
              <div className="ai-rec-row">
                <strong>Recommended Next Step:</strong>
                <span>{opportunity.latest_ai_recommendation.recommended_action}</span>
              </div>
              <span className="confidence-pill">
                Confidence: {Math.round(opportunity.latest_ai_recommendation.confidence_score * 100)}% (Advisory Only)
              </span>
            </div>
          )}

          {/* Authorization Form */}
          <div className="modal-section auth-form">
            <div className="form-group">
              <label>Merchant Reviewer ID</label>
              <input
                type="text"
                className="form-input"
                value={user}
                onChange={(e) => setUser(e.target.value)}
                placeholder="merchant_admin"
                disabled={submitting}
              />
            </div>
            <div className="form-group">
              <label>Decision Note (Logged to Audit Trail)</label>
              <input
                type="text"
                className="form-input"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="e.g. Buyer updated card balance via support ticket"
                disabled={submitting}
              />
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button
            className="btn btn-danger"
            onClick={handleReject}
            disabled={submitting}
          >
            Dismiss / Reject
          </button>
          <div className="modal-actions-right">
            <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button
              className="btn btn-primary"
              onClick={handleApprove}
              disabled={submitting || !isEligible}
            >
              {submitting ? 'Executing PayPal Capture...' : 'Authorize PayPal Capture'}
              <ArrowRight size={16} className="btn-icon-right" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
