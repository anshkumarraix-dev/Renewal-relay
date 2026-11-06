import React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Database,
  Server,
  RefreshCw,
  Clock,
  Radio,
} from 'lucide-react';
import type { HealthResponse } from '../types/health';

interface SystemStatusCardProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefresh: () => void;
}

export const SystemStatusCard: React.FC<SystemStatusCardProps> = ({
  health,
  loading,
  onRefresh,
}) => {
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'operational':
        return <CheckCircle2 className="status-icon icon-success" size={20} />;
      case 'degraded':
        return <AlertTriangle className="status-icon icon-warning" size={20} />;
      default:
        return <XCircle className="status-icon icon-danger" size={20} />;
    }
  };

  const getStatusClass = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'operational':
        return 'status-pill pill-success';
      case 'degraded':
        return 'status-pill pill-warning';
      default:
        return 'status-pill pill-danger';
    }
  };

  return (
    <div className="card status-card">
      <div className="card-header">
        <div className="card-header-title">
          <Radio size={20} className="card-header-icon" />
          <h2>System Foundation Diagnostics</h2>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="btn-refresh"
          title="Refresh Health Diagnostics"
        >
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          <span>{loading ? 'Probing...' : 'Refresh Status'}</span>
        </button>
      </div>

      <div className="status-grid">
        {/* Overall Status */}
        <div className="status-tile overall-tile">
          <div className="tile-header">
            <span className="tile-label">Overall Health</span>
            <span className={getStatusClass(health?.status || 'unhealthy')}>
              {health?.status?.toUpperCase() || 'OFFLINE'}
            </span>
          </div>
          <div className="tile-body">
            <div className="tile-value-row">
              {getStatusIcon(health?.status || 'unhealthy')}
              <span className="tile-value">
                {health?.status === 'healthy'
                  ? 'All Core Subsystems Operational'
                  : health?.status === 'degraded'
                  ? 'Subsystem Degraded'
                  : 'Backend Service Unreachable'}
              </span>
            </div>
            <div className="tile-meta">
              <Clock size={14} />
              <span>
                Checked: {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : 'Never'}
              </span>
            </div>
          </div>
        </div>

        {/* FastAPI Application Status */}
        <div className="status-tile">
          <div className="tile-header">
            <div className="tile-header-left">
              <Server size={18} className="tile-icon" />
              <span className="tile-label">FastAPI Engine</span>
            </div>
            <span className={getStatusClass(health?.app?.status || 'error')}>
              {health?.app?.status?.toUpperCase() || 'DOWN'}
            </span>
          </div>
          <div className="tile-body">
            <p className="tile-desc">{health?.app?.message || 'Awaiting connection...'}</p>
            <div className="tile-footer">
              <span className="metric-tag">Runtime: Python 3.14</span>
              <span className="metric-tag">FastAPI v0.162</span>
            </div>
          </div>
        </div>

        {/* SQLite Database Status */}
        <div className="status-tile">
          <div className="tile-header">
            <div className="tile-header-left">
              <Database size={18} className="tile-icon" />
              <span className="tile-label">SQLite Store</span>
            </div>
            <span className={getStatusClass(health?.database?.status || 'error')}>
              {health?.database?.status?.toUpperCase() || 'DISCONNECTED'}
            </span>
          </div>
          <div className="tile-body">
            <p className="tile-desc">
              {health?.database?.message || 'Database connection pending...'}
            </p>
            <div className="tile-footer">
              <span className="metric-tag">
                Latency: {health?.database?.latency_ms != null ? `${health.database.latency_ms} ms` : 'N/A'}
              </span>
              <span className="metric-tag">ORM: SQLAlchemy 2.0</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
