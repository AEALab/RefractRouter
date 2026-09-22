import profiles from '../../../../../data/model-profiles-v2.json' with { type: 'json' }

export interface FrozenPriceTier {
  id: string
  conditions: Record<string, unknown>
  prices: Record<string, number>
  budgetPricing: Record<string, number>
}

export interface FrozenModelProfile {
  provider: string
  model: string
  effective_model?: string
  pricing: { unit: string; inputPer1k: number; cachedInputPer1k: number; outputPer1k: number }
  pricing_basis?: { kind?: string; equivalence?: string; manufacturer?: string;
    actualProviderBilling?: boolean; note?: string }
  pricing_schedule?: { unit: string; perTokens: number; dimensions: string[]; tiers: FrozenPriceTier[] }
  pricing_materialization?: { strategy?: string; selectedTier?: string; note?: string }
  quality: number | null
  latencyMs: number | null
  sources: Array<{ kind: string; url: string; retrieved_at: string; metric_version: string }>
}

interface FrozenProfileCatalog {
  schema_version: string
  frozen_at: string
  pricing_policy: { method: string; note: string }
  profiles: FrozenModelProfile[]
}

/** 浏览器构建时内嵌 Python 核心的同一份冻结档案；这里只做展示，不计算路由。 */
export const FROZEN_MODEL_PROFILES = profiles as FrozenProfileCatalog

export function frozenModelProfile(provider: string, model: string): FrozenModelProfile | undefined {
  return FROZEN_MODEL_PROFILES.profiles.find(row => row.provider === provider && row.model === model)
}

export function formatUsdPricePer1k(value: number): string {
  const perMillion = value * 1000
  const million = perMillion.toLocaleString('en-US', { maximumFractionDigits: 6 })
  const thousand = value.toLocaleString('en-US', { maximumFractionDigits: 9 })
  return `$${million}/1M · $${thousand}/1k`
}

export function formatPriceConditions(conditions: Record<string, unknown>): string {
  return Object.entries(conditions).map(([key, value]) => `${key}: ${String(value)}`).join(' · ')
}
