/**
 * Analytics and KPI Types for Executive Dashboard.
 */

export interface OverviewMetrics {
  total_subscriptions: number;
  active_subscriptions: number;
  suspended_subscriptions: number;
  failed_renewals_count: number;
  eligible_recovery_opportunities: number;
  pending_approvals: number;
  verified_recovered_revenue: number;
  outstanding_eligible_revenue: number;
  currency: string;
}

export interface RevenueMonthData {
  month: string;
  potential: number;
  recovered: number;
}

export interface RevenueMetrics {
  verified_recovered_revenue: number;
  outstanding_eligible_revenue: number;
  total_failed_revenue: number;
  recovery_rate_percentage: number;
  currency: string;
  revenue_by_month: RevenueMonthData[];
}

export interface RecoveryTimelineItem {
  day: string;
  attempts: number;
  success: number;
}

export interface RecoveryMetrics {
  total_attempts: number;
  successful_recoveries: number;
  failed_recoveries: number;
  ambiguous_operations: number;
  success_rate_percentage: number;
  attempts_timeline: RecoveryTimelineItem[];
}

export interface FailureCategoryItem {
  category: string;
  count: number;
  percentage: number;
  total_amount: number;
}

export interface FailureMetrics {
  total_failures: number;
  categories: FailureCategoryItem[];
  most_common_reason: string;
  repeated_failures_count: number;
}

export interface AIInsightItem {
  title: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  category: string;
  message: string;
  suggested_action: string;
  affected_subscriptions: number;
}

export interface AIInsightsResponse {
  insights: AIInsightItem[];
  generated_at: string;
}
