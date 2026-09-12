/** RefractAgent 设置卡片：自包含 chrome 与表单（不依赖官方卡片组件）。 */
import { useState } from 'react'
import { MODE_KEYS, type CardField, type LimitKey, type ModeKey, type RefractCardProjection } from '../settings-card.js'

export interface RefractCardOwnerProps {
  t: (key: string) => string
  useRefractCard: <T>(selector: (snapshot: RefractCardProjection) => T) => T
  editDefaultEffort(value: string): void
  editStrategyEffort(mode: ModeKey, value: string): void
  editStrategyModels(mode: ModeKey, text: string): void
  editLimit(key: LimitKey, checked: boolean): void
  editProviderJson(text: string): void
  resetField(field: CardField): void
  save(): void
  discard(): void
}

const EFFORTS = ['minimal', 'low', 'medium', 'high', 'xhigh']

const STRATEGY_LABEL_KEYS: Record<ModeKey, string> = {
  economy: 'strategyEconomy',
  balanced: 'strategyBalanced',
  quality: 'strategyQuality',
}

const css = [
  '.rra-card{border:1px solid var(--dsw-alias-border-l2,#d9d9d9);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;background:var(--dsw-alias-bg-layer-2,#fff)}',
  '.rra-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}',
  '.rra-toggle{font:inherit;font-size:13px;font-weight:600;color:var(--dsw-alias-label-primary,#1f2329);background:none;border:none;padding:0;cursor:pointer}',
  '.rra-toggle:hover{opacity:.8}',
  '.rra-badge{font-size:11px;line-height:17px;padding:1px 8px;border-radius:999px;background:var(--dsw-alias-bg-module-platform,#f2f3f5);color:var(--dsw-alias-label-secondary,#515c6b);white-space:nowrap}',
  '.rra-desc{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary,#8a939f)}',
  '.rra-body{display:flex;flex-direction:column;gap:12px;padding-top:4px}',
  '.rra-field{display:flex;flex-direction:column;gap:6px;padding:10px 0;border-top:1px solid var(--dsw-alias-border-l2,#ececf0)}',
  '.rra-label-row{display:flex;align-items:center;gap:8px}',
  '.rra-label{font-size:13px;font-weight:500;color:var(--dsw-alias-label-primary,#1f2329);flex:1}',
  '.rra-field-hint{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary,#8a939f)}',
  '.rra-select{height:32px;font:inherit;font-size:13px;color:var(--dsw-alias-label-primary,#1f2329);border:1px solid var(--dsw-alias-border-l2,#d9d9d9);border-radius:8px;background:var(--dsw-alias-bg-layer-3,#fff);padding:0 8px;max-width:220px}',
  '.rra-select:disabled,.rra-textarea:disabled{color:var(--dsw-alias-label-tertiary,#8a939f);cursor:default;opacity:.6}',
  '.rra-strategy{display:flex;flex-direction:column;gap:4px;padding:6px 0}',
  '.rra-strategy-name{font-size:12px;font-weight:500;color:var(--dsw-alias-label-secondary,#515c6b)}',
  '.rra-textarea{font:inherit;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-primary,#1f2329);border:1px solid var(--dsw-alias-border-l2,#d9d9d9);border-radius:8px;background:var(--dsw-alias-bg-layer-3,#fff);padding:6px 10px;resize:vertical}',
  '.rra-json{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}',
  '.rra-check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--dsw-alias-label-primary,#1f2329)}',
  '.rra-reset{font:inherit;font-size:12px;color:var(--dsw-alias-label-secondary,#515c6b);background:none;border:none;padding:0;cursor:pointer}',
  '.rra-reset:hover:not(:disabled){color:var(--dsw-alias-label-primary,#1f2329)}',
  '.rra-reset:disabled{cursor:default;opacity:.5}',
  '.rra-invalid{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-error,#e5484d)}',
  '.rra-actions{display:flex;gap:8px;padding-top:8px}',
  '.rra-button{font:inherit;font-size:13px;font-weight:500;color:var(--dsw-alias-bg-inversed,#fff);background:var(--dsw-alias-brand-primary,#4c6ef5);border:none;border-radius:8px;padding:6px 16px;cursor:pointer}',
  '.rra-button:disabled{cursor:default;opacity:.5}',
  '.rra-button-secondary{background:var(--dsw-alias-bg-module-platform,#f2f3f5);color:var(--dsw-alias-label-primary,#1f2329)}',
  '.rra-hint{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary,#8a939f)}',
].join('')

if (typeof document !== 'undefined' && document.querySelector('style[data-plugin-css="refractagent-settings-card"]') === null) {
  const tag = document.createElement('style')
  tag.dataset.pluginCss = 'refractagent-settings-card'
  tag.textContent = css
  document.head.appendChild(tag)
}

export function RefractCard(props: RefractCardOwnerProps) {
  const { t } = props
  const state = props.useRefractCard(snapshot => snapshot)
  const [expanded, setExpanded] = useState(false)

  if (state.status === 'unavailable') {
    return (
      <li className="rra-card">
        <div className="rra-head">
          <span className="rra-toggle">{t('title')}</span>
        </div>
        <p className="rra-hint">{t('unavailable')}</p>
      </li>
    )
  }

  const disabled = !state.writable || state.saving
  const provider = state.provider
  const effortSelect = (value: string | undefined, onEdit: (value: string) => void) => {
    const options = [...EFFORTS, ...(value !== undefined && !EFFORTS.includes(value) ? [value] : [])]
    return (
      <select className="rra-select" value={value ?? ''} disabled={disabled || !state.hasProvider}
        onChange={event => onEdit(event.target.value)}>
        <option value="">{t('effortDefault')}</option>
        {options.map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }

  return (
    <li className="rra-card">
      <div className="rra-head">
        <button type="button" className="rra-toggle" aria-expanded={expanded}
          onClick={() => setExpanded(value => !value)}>
          {(expanded ? t('collapse') : t('expand')) + ': ' + t('title')}
        </button>
        {state.dirty ? <span className="rra-badge">{t('unsaved')}</span> : null}
        {state.overriddenProvider || state.overriddenLimits
          ? <span className="rra-badge">{t('overridden')}</span> : null}
      </div>
      <p className="rra-desc">{t('description')}</p>
      {expanded ? (
        <div className="rra-body">
          {!state.hasProvider ? <p className="rra-hint">{t('providerAbsentHint')}</p> : null}
          <div className="rra-field">
            <div className="rra-label-row">
              <span className="rra-label">{t('defaultEffort')}</span>
              {state.overriddenProvider
                ? <button type="button" className="rra-reset" disabled={disabled}
                    onClick={() => props.resetField('providerConfig')}>{t('reset')}</button> : null}
            </div>
            <p className="rra-field-hint">{t('defaultEffortHint')}</p>
            {effortSelect(provider?.defaultReasoningEffort, value => props.editDefaultEffort(value))}
          </div>
          <div className="rra-field">
            <span className="rra-label">{t('strategies')}</span>
            {MODE_KEYS.map(mode => (
              <div key={mode} className="rra-strategy">
                <span className="rra-strategy-name">{t(STRATEGY_LABEL_KEYS[mode])}</span>
                {effortSelect(provider?.strategies?.[mode]?.reasoningEffort,
                  value => props.editStrategyEffort(mode, value))}
                <textarea className="rra-textarea" rows={2} disabled={disabled || !state.hasProvider}
                  placeholder={t('modelsLabel')}
                  value={(provider?.strategies?.[mode]?.models ?? []).join('\n')}
                  onChange={event => props.editStrategyModels(mode, event.target.value)} />
              </div>
            ))}
          </div>
          <div className="rra-field">
            <div className="rra-label-row">
              <span className="rra-label">{t('limitsTitle')}</span>
              {state.overriddenLimits
                ? <button type="button" className="rra-reset" disabled={disabled}
                    onClick={() => props.resetField('limits')}>{t('reset')}</button> : null}
            </div>
            <label className="rra-check">
              <input type="checkbox" disabled={disabled} checked={state.limits.relaxBudget === true}
                onChange={event => props.editLimit('relaxBudget', event.target.checked)} />
              <span>{t('relaxBudget')}</span>
            </label>
            <p className="rra-field-hint">{t('relaxBudgetHint')}</p>
            <label className="rra-check">
              <input type="checkbox" disabled={disabled} checked={state.limits.relaxContext === true}
                onChange={event => props.editLimit('relaxContext', event.target.checked)} />
              <span>{t('relaxContext')}</span>
            </label>
            <p className="rra-field-hint">{t('relaxContextHint')}</p>
          </div>
          <div className="rra-field">
            <span className="rra-label">{t('providerJsonTitle')}</span>
            <p className="rra-field-hint">{t('providerJsonHint')}</p>
            <textarea className="rra-textarea rra-json" rows={8} disabled={disabled} spellCheck={false}
              value={state.providerJson}
              onChange={event => props.editProviderJson(event.target.value)} />
            {state.providerJsonError !== null
              ? <p className="rra-invalid">{t('invalidJson') + ': ' + state.providerJsonError}</p> : null}
          </div>
          <div className="rra-actions">
            <button type="button" className="rra-button" disabled={disabled || !state.dirty}
              onClick={() => props.save()}>{state.saving ? t('saving') : t('save')}</button>
            <button type="button" className="rra-button rra-button-secondary" disabled={disabled || !state.dirty}
              onClick={() => props.discard()}>{t('discard')}</button>
          </div>
          {state.failed ? <p className="rra-invalid">{t('saveFailed')}</p> : null}
        </div>
      ) : null}
    </li>
  )
}
