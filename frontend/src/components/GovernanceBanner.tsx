import React from 'react';
import { ShieldCheck, Lock, Cpu, CheckCircle } from 'lucide-react';
import type { GovernanceMetadata, PayPalMetadata } from '../types/health';

interface GovernanceBannerProps {
  governance?: GovernanceMetadata;
  paypal?: PayPalMetadata;
}

export const GovernanceBanner: React.FC<GovernanceBannerProps> = ({
  governance,
  paypal,
}) => {
  return (
    <div className="card governance-card">
      <div className="card-header">
        <div className="card-header-title">
          <ShieldCheck size={20} className="card-header-icon" />
          <h2>Architectural Boundaries & Security Guarantees</h2>
        </div>
        <span className="badge sandbox-badge">
          {paypal?.mode ? `MODE: ${paypal.mode.toUpperCase()}` : 'MODE: SANDBOX'}
        </span>
      </div>

      <div className="governance-grid">
        <div className="governance-item">
          <div className="item-icon-wrapper">
            <Lock size={18} />
          </div>
          <div className="item-content">
            <h3>Zero Credential Storage</h3>
            <p>
              Raw card numbers, CVVs, and banking details are never handled, processed, or persisted.
              Client secrets remain isolated in backend server memory.
            </p>
          </div>
        </div>

        <div className="governance-item">
          <div className="item-icon-wrapper">
            <ShieldCheck size={18} />
          </div>
          <div className="item-content">
            <h3>PayPal Payment Authority</h3>
            <p>
              PayPal is the sole payment authority. Payment results are never fabricated or simulated
              as real settlements; external PayPal verification is mandatory.
            </p>
          </div>
        </div>

        <div className="governance-item">
          <div className="item-icon-wrapper">
            <Cpu size={18} />
          </div>
          <div className="item-content">
            <h3>Deterministic Policy Gates</h3>
            <p>
              AI models provide diagnostic intelligence and recovery classification only.
              Autonomous payment execution by AI is strictly blocked by deterministic code policies.
            </p>
          </div>
        </div>

        <div className="governance-item">
          <div className="item-icon-wrapper">
            <CheckCircle size={18} />
          </div>
          <div className="item-content">
            <h3>Merchant Authorization</h3>
            <p>
              All renewal retry actions, recovery schedules, and customer interactions require explicit
              merchant authorization rules before any PayPal API dispatch.
            </p>
          </div>
        </div>
      </div>

      <div className="governance-footer">
        <span className="policy-indicator">
          Policy Status:{' '}
          <strong>
            {governance?.deterministic_policy_enforced
              ? 'Deterministic Enforcement Active'
              : 'Policy Unverified'}
          </strong>
        </span>
        <span className="policy-indicator">
          AI Autonomous Payment:{' '}
          <strong className="text-danger">
            {governance?.ai_autonomous_payment_allowed ? 'Allowed (UNSAFE)' : 'Prohibited (Enforced)'}
          </strong>
        </span>
      </div>
    </div>
  );
};
