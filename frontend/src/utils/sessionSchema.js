/**
 * Schema for the 25 public replay-session fields (API_CONTRACT) and the 20 model features
 * (reports/intent_baseline/feature_columns.json).
 */
import featureColumns from '@/data/reports/feature_columns.json'
import {
  formatBoolInt,
  formatDuration,
  formatInt,
  formatPriceUnits,
  formatRatio,
  formatUtcTime,
  formatWeekday,
} from './formatters'

export const SAFE_EVENT_PHASES = ['before_first_cart', 'at_first_cart_second', 'same_second_other']

/** The exact 20 model input features, in training order. */
export const PREDICT_FEATURES = featureColumns.features

const T = {
  id: (v) => v ?? '—',
  ts: formatUtcTime,
  ids: (v) => (v ? String(v).split(',').join(', ') : '—'),
  int: formatInt,
  bool: formatBoolInt,
  dur: (v) => (v === null || v === undefined ? '—' : `${formatDuration(v)} (${formatInt(v)} s)`),
  price: (v) => (v === null || v === undefined ? '—' : `${formatPriceUnits(v)} units`),
  ratio: formatRatio,
  hour: (v) => (v === null || v === undefined ? '—' : `${String(v).padStart(2, '0')}:00 UTC`),
  dow: (v) => (v === null || v === undefined ? '—' : `${formatWeekday(v)} (${v})`),
}

/** All 25 fields with label, group and formatter. */
export const SESSION_FIELDS = [
  { key: 'id', label: 'Replay ID', group: 'Identity', fmt: T.id },
  { key: 'session_start', label: 'Session start', group: 'Timing', fmt: T.ts },
  { key: 'first_cart_time', label: 'First cart time', group: 'Timing', fmt: T.ts },
  { key: 'seconds_to_first_cart', label: 'Seconds to first cart', group: 'Timing', fmt: T.dur },
  { key: 'hour_of_day_utc', label: 'Hour of day (UTC)', group: 'Timing', fmt: T.hour },
  { key: 'day_of_week_utc', label: 'Day of week (UTC)', group: 'Timing', fmt: T.dow },
  { key: 'views_before_cart', label: 'Views before cart', group: 'Browse', fmt: T.int },
  { key: 'has_view_before_cart', label: 'Has view before cart', group: 'Browse', fmt: T.bool },
  { key: 'unique_products_viewed_before_cart', label: 'Unique products viewed', group: 'Browse', fmt: T.int },
  { key: 'unique_categories_viewed_before_cart', label: 'Unique categories viewed', group: 'Browse', fmt: T.int },
  { key: 'unique_brands_viewed_before_cart', label: 'Unique brands viewed', group: 'Browse', fmt: T.int },
  { key: 'removes_before_cart', label: 'Removes before cart', group: 'Browse', fmt: T.int },
  { key: 'unique_products_removed_before_cart', label: 'Unique products removed', group: 'Browse', fmt: T.int },
  { key: 'cart_product_ids_at_first_cart_sec', label: 'Cart product IDs (first cart)', group: 'Cart', fmt: T.ids },
  { key: 'cart_category_ids_at_first_cart_sec', label: 'Cart category IDs (first cart)', group: 'Cart', fmt: T.ids },
  { key: 'cart_events_at_first_cart_sec', label: 'Cart events at first cart', group: 'Cart', fmt: T.int },
  { key: 'unique_products_carted_at_first_cart_sec', label: 'Unique products carted', group: 'Cart', fmt: T.int },
  { key: 'has_multi_products_at_first_cart_sec', label: 'Multi-product first cart', group: 'Cart', fmt: T.bool },
  { key: 'any_cart_brand_at_first_cart_sec', label: 'Branded cart item', group: 'Cart', fmt: T.bool },
  { key: 'avg_cart_price_at_first_cart_sec', label: 'Avg cart price', group: 'Price', fmt: T.price },
  { key: 'avg_viewed_price_before_cart', label: 'Avg viewed price', group: 'Price', fmt: T.price },
  { key: 'max_viewed_price_before_cart', label: 'Max viewed price', group: 'Price', fmt: T.price },
  { key: 'price_ratio_cart_to_view', label: 'Cart / view price ratio', group: 'Price', fmt: T.ratio },
  { key: 'user_prior_sessions', label: 'User prior sessions', group: 'History', fmt: T.int },
  { key: 'user_prior_purchase_sessions', label: 'User prior purchase sessions', group: 'History', fmt: T.int },
]
