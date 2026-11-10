import { useEffect, useState, useCallback } from 'react';
import { Header } from './components/Header';
import { OverviewTab } from './components/OverviewTab';
import { RecoveryQueueTab } from './components/RecoveryQueueTab';
import { SubscriptionsTab } from './components/SubscriptionsTab';
import { AIIntelligenceTab } from './components/AIIntelligenceTab';
import { AuditLogTab } from './components/AuditLogTab';
import { ApprovalModal } from './components/ApprovalModal';
import { GovernanceBanner } from './components/GovernanceBanner';
import {
  getSystemHealth,
  getOverviewMetrics,
  getRevenueMetrics,
  getRecoveryMetrics,
  getFailureMetrics,
  getAIInsights,
  getRecoveryOpportunities,
  getSubscriptions,
  approveRecovery,
  rejectRecovery,
  reconcileOperation,
  seedDemoData,
} from './api/client';
import type { HealthResponse } from './types/health';
import type { OverviewMetrics, RevenueMetrics, RecoveryMetrics, FailureMetrics, AIInsightItem } from './types/analytics';
import type { RecoveryOpportunity, SubscriptionItem } from './types/recovery';
import './App.css';

export function App() {
  const [activeTab, setActiveTab] = useState<string>('overview');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [overview, setOverview] = useState<OverviewMetrics | null>(null);
  const [revenue, setRevenue] = useState<RevenueMetrics | null>(null);
  const [recovery, setRecovery] = useState<RecoveryMetrics | null>(null);
  const [failures, setFailures] = useState<FailureMetrics | null>(null);
  const [insights, setInsights] = useState<AIInsightItem[]>([]);
  const [opportunities, setOpportunities] = useState<RecoveryOpportunity[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);

  const [loading, setLoading] = useState<boolean>(true);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [notification, setNotification] = useState<string | null>(null);
  const [selectedOpportunity, setSelectedOpportunity] = useState<RecoveryOpportunity | null>(null);

  const showNotification = (msg: string) => {
    setNotification(msg);
    setTimeout(() => setNotification(null), 4000);
  };

  const loadAllData = useCallback(async () => {
    setLoading(true);
    try {
      const [
        healthData,
        overviewData,
        revData,
        recData,
        failData,
        aiData,
        oppsData,
        subsData,
      ] = await Promise.allSettled([
        getSystemHealth(),
        getOverviewMetrics(),
        getRevenueMetrics(),
        getRecoveryMetrics(),
        getFailureMetrics(),
        getAIInsights(),
        getRecoveryOpportunities(),
        getSubscriptions(),
      ]);

      if (healthData.status === 'fulfilled') setHealth(healthData.value);
      if (overviewData.status === 'fulfilled') setOverview(overviewData.value);
      if (revData.status === 'fulfilled') setRevenue(revData.value);
      if (recData.status === 'fulfilled') setRecovery(recData.value);
      if (failData.status === 'fulfilled') setFailures(failData.value);
      if (aiData.status === 'fulfilled') setInsights(aiData.value.insights);
      if (oppsData.status === 'fulfilled') setOpportunities(oppsData.value);
      if (subsData.status === 'fulfilled') setSubscriptions(subsData.value);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let isMounted = true;
    const fetchInitialData = async () => {
      try {
        const [
          healthData,
          overviewData,
          revData,
          recData,
          failData,
          aiData,
          oppsData,
          subsData,
        ] = await Promise.allSettled([
          getSystemHealth(),
          getOverviewMetrics(),
          getRevenueMetrics(),
          getRecoveryMetrics(),
          getFailureMetrics(),
          getAIInsights(),
          getRecoveryOpportunities(),
          getSubscriptions(),
        ]);

        if (!isMounted) return;
        if (healthData.status === 'fulfilled') setHealth(healthData.value);
        if (overviewData.status === 'fulfilled') setOverview(overviewData.value);
        if (revData.status === 'fulfilled') setRevenue(revData.value);
        if (recData.status === 'fulfilled') setRecovery(recData.value);
        if (failData.status === 'fulfilled') setFailures(failData.value);
        if (aiData.status === 'fulfilled') setInsights(aiData.value.insights);
        if (oppsData.status === 'fulfilled') setOpportunities(oppsData.value);
        if (subsData.status === 'fulfilled') setSubscriptions(subsData.value);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchInitialData();

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSeedDemo = async () => {
    setSeeding(true);
    try {
      const res = await seedDemoData();
      showNotification(`✓ ${res.message}`);
      await loadAllData();
    } catch (err: unknown) {
      showNotification(`Failed to seed demo data: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setSeeding(false);
    }
  };

  const handleApprove = async (oppId: string, user: string, note?: string) => {
    const updated = await approveRecovery(oppId, user, note);
    showNotification(`✓ Successfully authorized recovery for ${updated.subscription_id}!`);
    await loadAllData();
  };

  const handleReject = async (oppId: string, user: string, note?: string) => {
    const updated = await rejectRecovery(oppId, user, note);
    showNotification(`Opportunity ${updated.subscription_id} dismissed.`);
    await loadAllData();
  };

  const handleReconcile = async (opId: string) => {
    const res = await reconcileOperation(opId);
    showNotification(`✓ ${res.message}`);
    await loadAllData();
  };

  return (
    <div className="app-container">
      <Header
        environment={health?.environment || 'development'}
        version={health?.version || '0.1.0'}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onSeedDemo={handleSeedDemo}
        seeding={seeding}
      />

      {notification && (
        <div className="toast-notification">
          <span>{notification}</span>
        </div>
      )}

      <main className="main-content">
        <GovernanceBanner
          governance={health?.governance}
          paypal={health?.paypal}
        />

        {activeTab === 'overview' && (
          <OverviewTab
            overview={overview}
            revenue={revenue}
            failures={failures}
            recovery={recovery}
            loading={loading}
            onRefresh={loadAllData}
          />
        )}

        {activeTab === 'recovery' && (
          <RecoveryQueueTab
            opportunities={opportunities}
            loading={loading}
            onRefresh={loadAllData}
            onSelectOpportunity={(opp) => setSelectedOpportunity(opp)}
          />
        )}

        {activeTab === 'subscriptions' && (
          <SubscriptionsTab
            subscriptions={subscriptions}
            loading={loading}
            onRefresh={loadAllData}
          />
        )}

        {activeTab === 'insights' && (
          <AIIntelligenceTab
            insights={insights}
          />
        )}

        {activeTab === 'audit' && (
          <AuditLogTab
            opportunities={opportunities}
            loading={loading}
            onRefresh={loadAllData}
            onReconcile={handleReconcile}
          />
        )}
      </main>

      <ApprovalModal
        opportunity={selectedOpportunity}
        onClose={() => setSelectedOpportunity(null)}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}

export default App;
