/** RefractAgent 设置卡片：遵循宿主卡片外观与表单交互。 */
import { useState } from 'react'
import examples from '../provider-examples.json' with { type: 'json' }
import { afpMetadata, candidateChoices, MODE_KEYS, type CardField, type LimitKey, type ModeKey, type RefractCardProjection } from '../settings-card.js'

export interface RefractCardOwnerProps {
  t: (key: string) => string
  useRefractCard: <T>(selector: (snapshot: RefractCardProjection) => T) => T
  editDefaultEffort(value: string): void
  editStrategyEffort(mode: ModeKey, value: string): void
  editStrategyAfpCeiling(mode: ModeKey, value: string): void
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

const css = `
.rra-card{border:1px solid var(--dsw-alias-border-l2);border-radius:12px;list-style:none;background:var(--dsw-alias-bg-layer-3);transition:border-color .16s,background .16s}
.rra-card:hover,.rra-card-open{border-color:var(--dsw-alias-label-dimmed)}
.rra-card-open{background:var(--dsw-alias-bg-layer-2)}
.rra-head{appearance:none;width:100%;font:inherit;color:inherit;text-align:left;cursor:pointer;background:none;border:0;border-radius:12px;display:flex;align-items:center;gap:12px;padding:14px 16px}
.rra-head-text{display:flex;flex:1;flex-direction:column;gap:4px;min-width:0}
.rra-name{color:var(--dsw-alias-label-primary);font-size:15px;font-weight:600;line-height:1.4}
.rra-desc{color:var(--dsw-alias-label-tertiary);font-size:13px;line-height:1.5}
.rra-chevron{color:var(--dsw-alias-label-tertiary);flex:none;transition:transform .16s}
.rra-card-open .rra-chevron{transform:rotate(180deg)}
.rra-body{border-top:1px solid var(--dsw-alias-border-l2);margin:0 16px;padding-bottom:8px}
.rra-badge{white-space:nowrap;background:var(--dsw-alias-bg-module-platform);color:var(--dsw-alias-label-secondary);border-radius:999px;padding:1px 8px;font-size:11px;font-weight:500;line-height:17px}
.rra-field{display:flex;flex-direction:column;gap:8px;padding:16px 0;border-bottom:1px solid var(--dsw-alias-border-l2)}
.rra-label-row{display:flex;align-items:center;gap:8px}
.rra-label{font-size:13px;font-weight:500;color:var(--dsw-alias-label-primary);flex:1}
.rra-field-hint,.rra-hint{margin:0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-tertiary);overflow-wrap:anywhere}
.rra-hint{margin-top:12px}
.rra-select,.rra-textarea{box-sizing:border-box;font:inherit;font-size:13px;color:var(--dsw-alias-label-primary);border:1px solid var(--dsw-alias-border-l2);border-radius:8px;background:var(--dsw-alias-bg-layer-3);padding:8px 10px}
.rra-select{height:34px;width:220px;max-width:100%}
.rra-textarea{width:100%;min-height:76px;line-height:1.5;resize:vertical}
.rra-textarea::placeholder{color:var(--dsw-alias-label-tertiary)}
.rra-select:disabled,.rra-textarea:disabled{opacity:.4;cursor:default}
.rra-strategy{display:flex;flex-direction:column;gap:12px;margin-top:16px;padding:20px 16px;border:1px solid var(--dsw-alias-border-l2);border-radius:10px;background:var(--dsw-alias-bg-layer-3);min-width:0}
.rra-strategy-name{margin:0;padding-bottom:12px;border-bottom:1px solid var(--dsw-alias-border-l2);font-size:15px;font-weight:600;line-height:1.4;color:var(--dsw-alias-label-primary)}
.rra-models{display:flex;flex-direction:column;gap:8px;border:0;margin:0;padding:4px 0;min-width:0}
.rra-models legend{padding:0;margin-bottom:6px}
.rra-models .rra-reset{align-self:flex-start;padding:0}
.rra-json{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;min-height:240px}
.rra-check{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--dsw-alias-label-primary)}
.rra-reset{font:inherit;font-size:12px;color:var(--dsw-alias-label-secondary);background:none;border:none;cursor:pointer}
.rra-invalid{margin:8px 0;font-size:12px;line-height:1.5;color:var(--dsw-alias-label-error)}
.rra-actions{display:flex;justify-content:flex-end;gap:8px;padding:12px 0 4px}
.rra-button{appearance:none;font:inherit;font-size:13px;line-height:1.5;cursor:pointer;border:1px solid transparent;border-radius:8px;padding:5px 14px;background:var(--dsw-alias-label-primary);color:var(--dsw-alias-bg-layer-3)}
.rra-button-secondary{border-color:var(--dsw-alias-border-l2);color:var(--dsw-alias-label-secondary);background:none}
.rra-button:disabled,.rra-reset:disabled{opacity:.4;cursor:default}
.rra-head:focus-visible,.rra-button:focus-visible,.rra-select:focus-visible,.rra-textarea:focus-visible{outline:2px solid var(--dsw-alias-brand-primary);outline-offset:1px}
`

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
          <span className="rra-name">{t('title')}</span>
        </div>
        <p className="rra-hint">{t('unavailable')}</p>
      </li>
    )
  }

  const disabled = state.status !== 'ready' || !state.writable || state.saving
  const provider = state.provider
  const choices = candidateChoices(provider)
  const effortSelect = (label: string, value: string | undefined, onEdit: (value: string) => void) => {
    const options = [...EFFORTS, ...(value !== undefined && !EFFORTS.includes(value) ? [value] : [])]
    return (
      <select className="rra-select" aria-label={label} value={value ?? ''} disabled={disabled}
        onChange={event => onEdit(event.target.value)}>
        <option value="">{t('effortDefault')}</option>
        {options.map(option => <option key={option} value={option}>{t('effort_' + option) === 'effort_' + option ? option : t('effort_' + option)}</option>)}
      </select>
    )
  }

  return (
    <li className={'rra-card' + (expanded ? ' rra-card-open' : '')}>
      <button type="button" className="rra-head" aria-expanded={expanded}
        aria-label={(expanded ? t('collapse') : t('expand')) + ': ' + t('title')}
        onClick={() => setExpanded(value => !value)}>
        <span className="rra-head-text">
          <span className="rra-name">{t('title')}</span>
          <span className="rra-desc">{t('description')}</span>
        </span>
        {state.dirty ? <span className="rra-badge">{t('unsaved')}</span> : null}
        <svg className="rra-chevron" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <path d="M3 5.5L7 9.5L11 5.5" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
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
            {effortSelect(t('defaultEffort'), provider?.defaultReasoningEffort, value => props.editDefaultEffort(value))}
          </div>
          <div className="rra-field">
            <span className="rra-label">{t('strategies')}</span>
            <p className="rra-field-hint">{t('separateControlsHint')}</p>
            {provider?.billingUnit === 'AFP' ? <p className="rra-field-hint">{t('afpSourceHint')} {afpMetadata.snapshotDate} · <a href={afpMetadata.sourceUrl} target="_blank" rel="noreferrer">{t('afpSource')}</a></p> : null}
            {MODE_KEYS.map(mode => {
              const selected = provider?.strategies?.[mode]?.models ?? []
              const missing = selected.filter(id => !choices.some(choice => choice.id === id))
              const update = (id: string, checked: boolean) => props.editStrategyModels(mode,
                (checked ? [...new Set([...selected, id])] : selected.filter(value => value !== id)).join('\n'))
              return (
                <section key={mode} className="rra-strategy" aria-label={t(STRATEGY_LABEL_KEYS[mode])}>
                  <h3 className="rra-strategy-name">{t(STRATEGY_LABEL_KEYS[mode])}</h3>
                  <p className="rra-field-hint">{t(STRATEGY_LABEL_KEYS[mode] + 'Hint')}</p>
                  {provider?.billingUnit === 'AFP' ? <label className="rra-label">
                    {t('afpCeiling')}
                    <select className="rra-select" style={{display:'block',marginTop:6}} disabled={disabled}
                      aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('afpCeiling')}
                      value={provider.strategies?.[mode]?.maxAfpCoefficient ?? ''}
                      onChange={event => props.editStrategyAfpCeiling(mode, event.target.value)}>
                      <option value="">{t('noCostCeiling')}</option>
                      {afpMetadata.tiers.map(value => <option key={value} value={value}>{t('afpAtMost')} {value}</option>)}
                    </select>
                  </label> : null}
                  <span className="rra-label">{t('modeEffort')}</span>
                  {effortSelect(t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('defaultEffort'), provider?.strategies?.[mode]?.reasoningEffort,
                    value => props.editStrategyEffort(mode, value))}
                  <fieldset className="rra-models" disabled={disabled}>
                    <legend className="rra-label">{t('modelsLabel')}</legend>
                    <p className="rra-field-hint">{t('modelsHint')}</p>
                    {choices.map(choice => (
                      <label key={choice.id} className="rra-check">
                        <input type="checkbox" checked={selected.includes(choice.id)}
                          aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + choice.label}
                          onChange={event => update(choice.id, event.target.checked)} />
                        <span>{choice.label}{choice.costLabel ? <small style={{display:'block'}} className="rra-field-hint">{choice.costLabel} · {choice.planLabel}</small> : null}</span>
                      </label>
                    ))}
                    {missing.map(id => (
                      <label key={id} className="rra-check">
                        <input type="checkbox" checked aria-label={t(STRATEGY_LABEL_KEYS[mode]) + ' · ' + t('missingModel') + ': ' + id}
                          onChange={() => update(id, false)} />
                        <span>{t('missingModel')}: {id}</span>
                      </label>
                    ))}
                    {choices.length === 0 ? <p className="rra-field-hint">{t('noModels')}</p> : null}
                    <p className="rra-field-hint">{selected.length ? t('selectedModels') + selected.length : t('allModels')}</p>
                    {selected.length ? <button type="button" className="rra-reset"
                      onClick={() => props.editStrategyModels(mode, '')}>{t('useAllModels')}</button> : null}
                  </fieldset>
                </section>
              )
            })}
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
            <div className="rra-label-row">
              <span className="rra-label">{t('providerJsonTitle')}</span>
              <button type="button" className="rra-reset" disabled={disabled}
                onClick={() => props.editProviderJson(JSON.stringify(examples['openai-compatible'], null, 2))}>{t('insertExample')}</button>
            </div>
            <p className="rra-field-hint">{t('providerJsonHint')}</p>
            <textarea className="rra-textarea rra-json" rows={12} disabled={disabled} spellCheck={false}
              aria-label={t('providerJsonTitle')} placeholder={JSON.stringify(examples['openai-compatible'], null, 2)}
              value={state.providerJson}
              onChange={event => props.editProviderJson(event.target.value)} />
            {state.providerJsonError !== null
              ? <p className="rra-invalid">{t('invalidJson') + ': ' + state.providerJsonError}</p> : null}
          </div>
          <div className="rra-actions">
            <button type="button" className="rra-button" disabled={disabled || !state.dirty || state.providerJsonError !== null}
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
