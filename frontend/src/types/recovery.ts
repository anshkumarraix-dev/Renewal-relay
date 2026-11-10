/**
 * Types for Recovery Opportunities, Policy Evaluations, AI Advice, Approvals, and Subscriptions.
 */

export interface RecoveryEvaluation {
  id: string;
  opportunity_id: string;
  is_eligible: boolean;
  decision: 'ELIGIBLE' | 'INELIGIBLE' | 'WAITING_NATIVE_RETRY' | 'REQUIRES_VERIFICATION' | 'COOLDOWN_ACTIVE';
  reason: string;
  evidence_json: Record<string, unknown>;
  policy_version: string;
  suggested_action: string;
  evaluated_at: string;
}

export interface AIRecommendation {
  id: string;
  opportunity_id: string;
  subscription_id: string;
  failure_category: string;
  confidence_score: number;
  explanation: string;
  evidence_json: {
    points: string[];
    missing?: string;
  };
  recommended_action: string;
  suggested_action_type: 'CAPTURE_BALANCE' | 'CONTACT_CUSTOMER' | 'WAIT_FOR_RETRY' | 'MANUAL_REVIEW';
  created_at: string;
}

export interface RecoveryOperation {
  id: string;
  opportunity_id: string;
  subscription_id: string;
  operation_type: string;
  request_id: string;
  amount: number;
  currency: string;
  status: 'INITIATED' | 'COMPLETED' | 'FAILED' | 'AMBIGUOUS';
  paypal_debug_id?: string;
  paypal_capture_id?: string;
  reconciled: boolean;
  reconciled_at?: string;
  created_at: string;
}

export interface RecoveryOpportunity {
  id: string;
  subscription_id: string;
  status: 'IDENTIFIED' | 'ELIGIBLE' | 'PENDING_APPROVAL' | 'APPROVED' | 'EXECUTING' | 'RECOVERED' | 'REJECTED' | 'AMBIGUOUS_RECONCILING' | 'UNRECOVERABLE';
  eligible_amount: number;
  currency: string;
  detected_at: string;
  resolved_at?: string;
  subscriber_name?: string;
  subscriber_email?: string;
  plan_name?: string;
  failed_payment_count: number;
  subscription_status?: string;
  latest_evaluation?: RecoveryEvaluation;
  latest_ai_recommendation?: AIRecommendation;
  latest_operation?: RecoveryOperation;
}

export interface SubscriptionItem {
  id: string;
  plan_id?: string;
  merchant_id?: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'CANCELLED' | 'EXPIRED';
  subscriber_name?: string;
  subscriber_email?: string;
  outstanding_balance_amount: number;
  currency: string;
  failed_payment_count: number;
  next_billing_time?: string;
  last_payment_time?: string;
  last_payment_amount?: number;
  created_at: string;
  updated_at: string;
}
