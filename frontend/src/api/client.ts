/**
 * API Client for Renewal Relay Backend.
 *
 * Base URL is driven by VITE_API_BASE_URL.
 * No sensitive secrets or credentials are ever handled on the frontend.
 */

import axios, { isAxiosError } from 'axios';
import type { HealthResponse, LivenessResponse } from '../types/health';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 8000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

/**
 * Fetch comprehensive system health status.
 * Returns the parsed HealthResponse whether HTTP 200 (healthy) or HTTP 503 (degraded).
 */
export async function getSystemHealth(): Promise<HealthResponse> {
  try {
    const response = await apiClient.get<HealthResponse>('/health');
    return response.data;
  } catch (error: unknown) {
    if (isAxiosError(error) && error.response?.data) {
      // Backend returned structured degraded response (e.g. HTTP 503)
      return error.response.data as HealthResponse;
    }
    const errorMessage = error instanceof Error ? error.message : 'Cannot connect to backend server';
    // Network or offline failure
    return {
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      environment: 'unknown',
      version: '0.1.0',
      app: {
        status: 'error',
        message: errorMessage,
      },
      database: {
        status: 'error',
        message: 'Backend service unreachable',
      },
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
