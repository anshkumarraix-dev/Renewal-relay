import React from 'react';
import { ShieldCheck, Database, Sparkles, Layers, ListFilter, AlertTriangle } from 'lucide-react';

interface HeaderProps {
  environment: string;
  version: string;
  activeTab: string;
  onTabChange: (tab: string) => void;
  onSeedDemo: () => void;
  seeding: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  environment,
  version,
  activeTab,
  onTabChange,
  onSeedDemo,
  seeding,
}) => {
  return (
    <header className="header-container">
      <div className="header-top">
        <div className="brand-section">
          <div className="brand-logo">
            <span className="logo-icon">⚡</span>
            <div className="brand-titles">
              <div className="brand-name-row">
                <h1>Renewal Relay</h1>
                <span className="badge sandbox-badge">PayPal Sandbox</span>
                <span className="badge env-badge">{environment}</span>
                <span className="badge version-badge">v{version}</span>
              </div>
              <p className="brand-subtitle">AI-Powered Subscription Renewal Recovery & Merchant Intelligence</p>
            </div>
          </div>
        </div>

        <div className="header-actions">
          <button
            className="btn btn-secondary seed-btn"
            onClick={onSeedDemo}
            disabled={seeding}
            title="Populate realistic PayPal Sandbox subscriptions and failure events for testing"
          >
            <Database className="btn-icon" size={16} />
            {seeding ? 'Seeding Sandbox...' : 'Seed Sandbox Demo'}
          </button>
          <div className="env-pill">
            <ShieldCheck size={14} className="text-emerald" />
            <span>Gov Policy: Enforced</span>
          </div>
        </div>
      </div>

      <nav className="nav-tabs">
        <button
          className={`nav-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => onTabChange('overview')}
        >
          <Layers size={16} />
          Executive Overview
        </button>
        <button
          className={`nav-tab ${activeTab === 'recovery' ? 'active' : ''}`}
          onClick={() => onTabChange('recovery')}
        >
          <Sparkles size={16} />
          Recovery Queue & Approvals
        </button>
        <button
          className={`nav-tab ${activeTab === 'subscriptions' ? 'active' : ''}`}
          onClick={() => onTabChange('subscriptions')}
        >
          <ListFilter size={16} />
          Subscriptions Monitor
        </button>
        <button
          className={`nav-tab ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => onTabChange('insights')}
        >
          <AlertTriangle size={16} />
          AI Merchant Intelligence
        </button>
        <button
          className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`}
          onClick={() => onTabChange('audit')}
        >
          <ShieldCheck size={16} />
          Audit & Reconciliation
        </button>
      </nav>
    </header>
  );
};
