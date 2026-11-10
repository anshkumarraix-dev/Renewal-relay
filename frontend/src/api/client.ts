/**
 * API Client for Renewal Relay Backend.
 *
 * Base URL is driven by VITE_API_BASE_URL.
 * No sensitive secrets or credentials are ever handled on the frontend.
 */

import axios, { isAxiosError } from 'axios';
import type { HealthResponse, LivenessResponse } from '../types/health';
import type {
  OverviewMetrics,
  RevenueMetrics,
  RecoveryMetrics,
  FailureMetrics,
  AIInsightsResponse,
} from '../types/analytics';
import type {
  RecoveryOpportunity,
  SubscriptionItem,
} from '../types/recovery';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

/**
 * Fetch comprehensive system health status.
 */
export async function getSystemHealth(): Promise<HealthResponse> {
  try {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  } catch (error: unknown) {
    if (isAxiosError(error) && error.response?.data) {
      return error.response.data as HealthResponse;
    }
    const errorMessage = error instanceof Error ? error.message : 'Cannot connect to backend server';
    return {
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      environment: 'unknown',
      version: '0.1.0',
      app: { status: 'error', message: errorMessage },
      database: { status: 'error', message: 'Backend service unreachable' },
      paypal: {
        mode: 'sandbox',
        status: 'disconnected',
        external_polling: false,
        notice: 'Backend unreachable',
      },
      governance: {
        deterministic_policy_enforced: true,
        ai_autonomous_payment_allowed: false,
        payment_authority: 'PayPal',
      },
    };
  }
}

/**
 * Perform basic liveness probe.
 */
export async function getLiveness(): Promise<LivenessResponse> {
  const response = await apiClient.get<LivenessResponse>('/health/live');
  return response.data;
}

/**
 * Overview KPI metrics.
 */
export async function getOverviewMetrics(): Promise<OverviewMetrics> {
  const res = await apiClient.get<OverviewMetrics>('/analytics/overview');
  return res.data;
}

/**
 * Revenue distribution and recovery rate metrics.
 */
export async function getRevenueMetrics(): Promise<RevenueMetrics> {
  const res = await apiClient.get<RevenueMetrics>('/analytics/revenue');
  return res.data;
}

/**
 * Recovery operations statistics.
 */
export async function getRecoveryMetrics(): Promise<RecoveryMetrics> {
  const res = await apiClient.get<RecoveryMetrics>('/analytics/recovery');
  return res.data;
}

/**
 * Failure category distribution.
 */
export async function getFailureMetrics(): Promise<FailureMetrics> {
  const res = await apiClient.get<FailureMetrics>('/analytics/failures');
  return res.data;
}

/**
 * AI merchant insights and alerts.
 */
export async function getAIInsights(): Promise<AIInsightsResponse> {
  const res = await apiClient.get<AIInsightsResponse>('/analytics/ai-insights');
  return res.data;
}

/**
 * List recovery opportunities.
 */
export async function getRecoveryOpportunities(status?: string): Promise<RecoveryOpportunity[]> {
  const params = status ? { status } : {};
  const res = await apiClient.get<RecoveryOpportunity[]>('/recovery/opportunities', { params });
  return res.data;
}

/**
 * Explicit merchant approval for capture.
 */
export async function approveRecovery(
  opportunityId: string,
  merchantUser: string = 'merchant_admin',
  note?: string,
): Promise<RecoveryOpportunity> {
  const res = await apiClient.post<RecoveryOpportunity>(`/recovery/opportunities/${opportunityId}/approve`, {
    merchant_user: merchantUser,
    decision_note: note,
  });
  return res.data;
}

/**
 * Explicit merchant dismissal / rejection.
 */
export async function rejectRecovery(
  opportunityId: string,
  merchantUser: string = 'merchant_admin',
  note?: string,
): Promise<RecoveryOpportunity> {
  const res = await apiClient.post<RecoveryOpportunity>(`/recovery/opportunities/${opportunityId}/reject`, {
    merchant_user: merchantUser,
    decision_note: note,
  });
  return res.data;
}

/**
 * Reconcile ambiguous operation against PayPal transactions.
 */
export async function reconcileOperation(
  operationId: string,
  notes?: string,
): Promise<{ operation_id: string; reconciled_status: string; message: string }> {
  const res = await apiClient.post(`/recovery/operations/${operationId}/reconcile`, { notes });
  return res.data;
}

/**
 * List tracked subscriptions.
 */
export async function getSubscriptions(status?: string): Promise<SubscriptionItem[]> {
  const params = status ? { status } : {};
  const res = await apiClient.get<SubscriptionItem[]>('/subscriptions', { params });
  return res.data;
}

/**
 * Seed realistic PayPal Sandbox demo simulation data.
 */
export async function seedDemoData(): Promise<{ status: string; message: string; seeded_subscriptions: string[] }> {
  const res = await apiClient.post('/demo/seed');
  return res.data;
}
