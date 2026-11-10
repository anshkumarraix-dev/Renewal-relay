import React from 'react';
import { AlertTriangle, Sparkles, ShieldAlert, ArrowRight, CheckCircle2 } from 'lucide-react';
import type { AIInsightItem } from '../types/analytics';

interface AIIntelligenceTabProps {
  insights: AIInsightItem[];
}

export const AIIntelligenceTab: React.FC<AIIntelligenceTabProps> = ({
  insights,
}) => {
  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'HIGH':
        return <span className="badge badge-rose">High Priority</span>;
      case 'MEDIUM':
        return <span className="badge badge-amber">Medium Priority</span>;
      default:
        return <span className="badge badge-blue">Informational</span>;
    }
  };

  return (
    <div className="tab-pane insights-pane">
      <div className="pane-header">
        <div>
          <h2>AI Merchant Intelligence & Churn Radar</h2>
          <p className="pane-subtitle">
            Automated failure pattern discovery, involuntary churn alerts, and evidence-backed merchant advice
          </p>
        </div>
      </div>

      <div className="insights-grid">
        {insights.length === 0 ? (
          <div className="card py-12 text-center text-muted">
            <Sparkles size={32} className="mx-auto mb-3 text-indigo-400 opacity-60" />
            <p>No active alerts. Seed demo data to preview AI failure classification and churn radar insights.</p>
          </div>
        ) : (
          insights.map((item, index) => (
            <div key={index} className={`insight-card severity-${item.severity.toLowerCase()}`}>
              <div className="insight-header">
                <div className="insight-title-row">
                  {item.severity === 'HIGH' ? (
                    <ShieldAlert size={20} className="text-rose" />
                  ) : item.severity === 'MEDIUM' ? (
                    <AlertTriangle size={20} className="text-amber" />
                  ) : (
                    <Sparkles size={20} className="text-emerald" />
                  )}
                  <h3>{item.title}</h3>
                </div>
                {getSeverityBadge(item.severity)}
              </div>

              <div className="insight-body">
                <p className="insight-message">{item.message}</p>
                <div className="insight-action-box">
                  <strong className="action-title">
                    <ArrowRight size={14} className="inline-icon" /> Suggested Merchant Strategy:
                  </strong>
                  <p className="action-desc">{item.suggested_action}</p>
                </div>
              </div>

              <div className="insight-footer">
                <span className="affected-hint">
                  Impacts <strong>{item.affected_subscriptions}</strong> subscription(s)
                </span>
                <span className="category-hint font-mono">{item.category}</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Advisory Principles Card */}
      <div className="card governance-explainer-card mt-6">
        <div className="card-header">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-emerald" />
            <h3>Renewal Relay AI Governance Architecture</h3>
          </div>
        </div>
        <div className="card-body governance-rules-list">
          <div className="gov-rule-item">
            <strong>Advisory, Never Autonomous</strong>
            <p>AI provides root-cause classification and merchant suggestions. AI cannot independently execute charges or bypass policy checks.</p>
          </div>
          <div className="gov-rule-item">
            <strong>Calibrated Confidence & Explicit Evidence</strong>
            <p>Every analysis provides supporting evidence items and flags missing data when PayPal returns non-specific decline codes.</p>
          </div>
          <div className="gov-rule-item">
            <strong>Zero Raw Credential Exposure</strong>
            <p>Zero sensitive card or banking credentials are sent to AI models or stored in application logs.</p>
          </div>
        </div>
      </div>
    </div>
  );
};
