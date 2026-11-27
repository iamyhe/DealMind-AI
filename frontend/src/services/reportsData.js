/**
 * Team report data (REAL numbers, bundled as exact copies of the merged repo JSON files):
 *   - Role 4: reports/cart_analysis/cart_behavior_summary.json
 *   - Role 5: reports/intent_baseline/baseline_metrics.json + feature_columns.json
 *   - Data prep: data/processed/dataset_prep_summary.json
 * Copies live in src/data/reports/ (refresh by re-copying when the reports change).
 *
 * Role 3 (Funnel & Data Quality JSON) and Role 6 (Random Forest & final test evaluation)
 * are NOT merged yet and are exposed as explicit "Pending merge" placeholders — no invented metrics.
 */
import cartBehavior from '@/data/reports/cart_behavior_summary.json'
import baselineMetrics from '@/data/reports/baseline_metrics.json'
import featureColumns from '@/data/reports/feature_columns.json'
import datasetPrep from '@/data/reports/dataset_prep_summary.json'
import { settings } from './config'

// ---------------------------------------------------------------------------
// Data preparation (temporal split + cleaning rules)
// ---------------------------------------------------------------------------
export const DATA_PREP = {
  source: 'data/processed/dataset_prep_summary.json',
  rules: datasetPrep.cleaning_and_feature_rules,
  overall: datasetPrep.overall_funnel_all_valid_sessions,
  splits: [
    { key: 'train', label: 'Train', window: 'Oct 2 – Dec 31, 2019', ...datasetPrep.intent_datasets.train },
    { key: 'val', label: 'Validation', window: 'Jan 1 – Jan 31, 2020', ...datasetPrep.intent_datasets.val },
    { key: 'test', label: 'Test', window: 'Feb 1 – Feb 28, 2020', ...datasetPrep.intent_datasets.test },
  ],
  replay: {
    curatedSessions: datasetPrep.sqlite_database.curated_test_replay_sessions,
    events: datasetPrep.sqlite_database.replay_events_count,
  },
}

// ---------------------------------------------------------------------------
// Role 5 — Logistic Regression baseline
// ---------------------------------------------------------------------------
const VARIANT_LABELS = {
  no_class_weight: 'No class weight',
  balanced: 'Balanced class weight',
  log1p: 'log1p transform',
}

const selectedKey = baselineMetrics.selected
const sel = baselineMetrics.results[selectedKey]

export const BASELINE = {
  source: 'reports/intent_baseline/baseline_metrics.json',
  selected: selectedKey,
  selectedLabel: VARIANT_LABELS[selectedKey] ?? selectedKey,
  primaryMetric: baselineMetrics.primary_metric,
  rows: baselineMetrics.rows,
  intercept: baselineMetrics.intercept,
  sklearnVersion: baselineMetrics.sklearn_version,
  assumptions: baselineMetrics.assumptions,
  features: featureColumns.features,
  target: featureColumns.target,
  /** Validation (Jan 2020) metrics of the selected variant. Threshold = best-F1 on validation. */
  validation: {
    pr_auc: sel.pr_auc,
    roc_auc: sel.roc_auc,
    train_pr_auc: sel.train_pr_auc,
    f1: sel.at_best_f1.f1,
    precision: sel.at_best_f1.precision,
    recall: sel.at_best_f1.recall,
    threshold: sel.at_best_f1.threshold,
    at_05: sel['at_0.5'],
  },
  variants: Object.entries(baselineMetrics.results).map(([key, r]) => ({
    key,
    label: VARIANT_LABELS[key] ?? key,
    selected: key === selectedKey,
    train_pr_auc: r.train_pr_auc,
    pr_auc: r.pr_auc,
    roc_auc: r.roc_auc,
    best: r.at_best_f1,
    at05: r['at_0.5'],
  })),
  coefficients: [...baselineMetrics.coefficients].sort((a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient)),
  /** No-skill PR-AUC reference = validation positive rate (from dataset_prep_summary.json). */
  noSkillPrAuc: datasetPrep.intent_datasets.val.positive_rate_pct / 100,
}

// ---------------------------------------------------------------------------
// Model comparison rows (Role 5 real, Role 6 pending)
// ---------------------------------------------------------------------------
export const MODEL_ROWS = [
  {
    key: 'lr',
    name: 'Logistic Regression',
    role: 'Baseline — Role 5',
    status: 'available',
    split: 'Validation · Jan 2020',
    metrics: {
      pr_auc: BASELINE.validation.pr_auc,
      roc_auc: BASELINE.validation.roc_auc,
      f1: BASELINE.validation.f1,
      precision: BASELINE.validation.precision,
      recall: BASELINE.validation.recall,
    },
    threshold: BASELINE.validation.threshold,
  },
  {
    key: 'rf',
    name: 'Random Forest',
    role: 'Final Candidate — Role 6',
    status: 'pending',
    statusLabel: 'Pending Role 6 merge',
    split: 'Final test · Feb 2020',
    metrics: null,
    threshold: null,
  },
]

export const METRIC_COLUMNS = [
  { key: 'pr_auc', label: 'PR-AUC' },
  { key: 'roc_auc', label: 'ROC-AUC' },
  { key: 'f1', label: 'F1' },
  { key: 'precision', label: 'Precision' },
  { key: 'recall', label: 'Recall' },
]

// ---------------------------------------------------------------------------
// Role 4 — Cart behavior & catalog
// ---------------------------------------------------------------------------
export const CART_BEHAVIOR = {
  source: 'reports/cart_analysis/cart_behavior_summary.json',
  meta: cartBehavior.meta,
  numeric: cartBehavior.pre_cart_behavior.numeric_comparison,
  flags: cartBehavior.pre_cart_behavior.flag_comparison,
  byBucket: {
    seconds_to_first_cart: cartBehavior.pre_cart_behavior.purchase_rate_by_seconds_to_first_cart,
    views_before_cart: cartBehavior.pre_cart_behavior.purchase_rate_by_views_before_cart,
    removes_before_cart: cartBehavior.pre_cart_behavior.purchase_rate_by_removes_before_cart,
    prior_purchase_sessions: cartBehavior.pre_cart_behavior.purchase_rate_by_prior_purchase_sessions,
    has_view: cartBehavior.pre_cart_behavior.purchase_rate_by_has_view,
    hour_utc: cartBehavior.pre_cart_behavior.purchase_rate_by_hour_utc.map((r) => ({
      bucket: String(r.hour).padStart(2, '0'),
      sessions: r.sessions,
      purchase_rate: r.purchase_rate,
    })),
    weekday_utc: cartBehavior.pre_cart_behavior.purchase_rate_by_weekday_utc.map((r) => ({
      bucket: r.weekday,
      sessions: r.sessions,
      purchase_rate: r.purchase_rate,
    })),
  },
  catalog: cartBehavior.catalog_and_brands,
  brand: cartBehavior.catalog_and_brands.brand_presence,
  priceBands: cartBehavior.price_band_cart_behavior,
}

// ---------------------------------------------------------------------------
// Pending slots
// ---------------------------------------------------------------------------
export const ROLE3_FUNNEL = {
  status: 'pending',
  statusLabel: 'Awaiting Role 3 Funnel & Data Quality JSON merge',
  expectedPath: 'reports/eda/funnel_summary.json',
}

export const ROLE6_MODEL = {
  status: 'pending',
  statusLabel: 'Pending Role 6 merge',
  expected: 'Random Forest validation + final Feb 2020 test evaluation and feature importances',
}

// ---------------------------------------------------------------------------
// Optional hooks for future backend report endpoints (disabled by default).
// Enable with VITE_ENABLE_REPORT_ENDPOINTS=true once the backend serves them.
// ---------------------------------------------------------------------------
export const REPORT_ENDPOINTS = {
  cartBehavior: '/api/reports/cart-behavior',
  funnel: '/api/reports/funnel',
  modelMetrics: '/api/reports/model-metrics',
}

const ENDPOINTS_ENABLED = String(import.meta.env.VITE_ENABLE_REPORT_ENDPOINTS ?? 'false').toLowerCase() === 'true'

/**
 * Try a live report endpoint, returning `fallback` (bundled data or pending slot) on any failure.
 * @param {'cartBehavior'|'funnel'|'modelMetrics'} name
 */
export async function fetchReport(name, fallback = null) {
  if (!ENDPOINTS_ENABLED || settings.mode === 'mock' || !REPORT_ENDPOINTS[name]) return { source: 'bundled', data: fallback }
  try {
    const res = await fetch(`${settings.baseUrl}${REPORT_ENDPOINTS[name]}`, { headers: { Accept: 'application/json' } })
    if (!res.ok) return { source: 'bundled', data: fallback }
    return { source: 'api', data: await res.json() }
  } catch {
    return { source: 'bundled', data: fallback }
  }
}
