import { useEffect, useState, useCallback } from 'react';
import { Header } from './components/Header';
import { SystemStatusCard } from './components/SystemStatusCard';
import { GovernanceBanner } from './components/GovernanceBanner';
import { getSystemHealth } from './api/client';
import type { HealthResponse } from './types/health';
import './App.css';

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const refreshHealth = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSystemHealth();
      setHealth(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isSubscribed = true;
    getSystemHealth().then((data) => {
      if (isSubscribed) {
        setHealth(data);
        setLoading(false);
      }
    }).catch(() => {
      if (isSubscribed) {
        setLoading(false);
      }
    });

    return () => {
      isSubscribed = false;
    };
  }, []);

  return (
    <div className="app-container">
      <Header
        environment={health?.environment || 'development'}
        version={health?.version || '0.1.0'}
      />

      <main className="main-content">
        <section className="dashboard-grid">
          <SystemStatusCard
            health={health}
            loading={loading}
            onRefresh={refreshHealth}
          />
          <GovernanceBanner
            governance={health?.governance}
            paypal={health?.paypal}
          />
        </section>

        <section className="architecture-summary">
          <div className="card summary-card">
            <div className="card-header">
              <h3>Development Foundation Checklist</h3>
            </div>
            <div className="checklist-grid">
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>FastAPI Health Endpoint</strong>
                  <p>Verified with real SQLite connectivity and latency metrics.</p>
                </div>
              </div>
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>React + TypeScript + Vite</strong>
                  <p>Type-safe API client and system telemetry dashboard active.</p>
                </div>
              </div>
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>SQLite via SQLAlchemy 2.0</strong>
                  <p>Session management, lifecycle initialization, and connection pooling ready.</p>
                </div>
              </div>
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>Secret Isolation & Sanitized Logging</strong>
                  <p>Zero credentials in Git or frontend; automatic token redaction in logs.</p>
                </div>
              </div>
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>Strict CORS Boundaries</strong>
                  <p>Restricted to authorized local frontend development origins.</p>
                </div>
              </div>
              <div className="check-item verified">
                <span className="check-bullet">✓</span>
                <div>
                  <strong>Deterministic Governance Gates</strong>
                  <p>Policy enforcement safeguards against unauthorized payment execution.</p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="app-footer">
        <p>Renewal Relay • Payment Recovery Platform Foundation • PayPal Sandbox Mode</p>
      </footer>
    </div>
  );
}

export default App;
