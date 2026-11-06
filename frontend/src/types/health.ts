/**
 * Type definitions for System Health and Component Diagnostics.
 */

export interface ComponentStatus {
  status: 'operational' | 'degraded' | 'error';
  latency_ms?: number | null;
  message?: string | null;
}

export interface PayPalMetadata {
  mode: string;
  status: string;
  external_polling: boolean;
  notice: string;
}

export interface GovernanceMetadata {
  deterministic_policy_enforced: boolean;
  ai_autonomous_payment_allowed: boolean;
  payment_authority: string;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp: string;
  environment: string;
  version: string;
  app: ComponentStatus;
  database: ComponentStatus;
  paypal: PayPalMetadata;
  governance: GovernanceMetadata;
}

export interface LivenessResponse {
  status: string;
  timestamp: string;
}
