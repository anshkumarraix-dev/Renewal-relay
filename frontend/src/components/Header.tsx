import React from 'react';
import { Shield, RefreshCw } from 'lucide-react';

interface HeaderProps {
  environment?: string;
  version?: string;
}

export const Header: React.FC<HeaderProps> = ({
  environment = 'development',
  version = '0.1.0',
}) => {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="logo-badge">
          <RefreshCw className="logo-icon" size={26} />
        </div>
        <div className="brand-text">
          <div className="brand-title-row">
            <h1>Renewal Relay</h1>
            <span className="badge env-badge">{environment.toUpperCase()}</span>
            <span className="badge version-badge">v{version}</span>
          </div>
          <p className="brand-subtitle">
            AI-Powered PayPal Subscription Renewal Recovery & Merchant Intelligence Platform
          </p>
        </div>
      </div>
      <div className="header-meta">
        <div className="security-pill">
          <Shield size={16} />
          <span>PayPal Sandbox Authority</span>
        </div>
      </div>
    </header>
  );
};
