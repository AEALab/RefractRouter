import { buildV4FeasibilityPreview, type ProviderConfigView, type V4CollectionKey,
  type V4DagMode, type V4DataMode } from '../settings-card.js'

type Row = Record<string, unknown>

export interface V4SettingsProps {
  t(key: string): string
  provider: ProviderConfigView
  disabled: boolean
  advanced: boolean
  editV4QualityMin(value: number): void
  editV4DagMode(value: V4DagMode): void
  editV4DataMode(value: V4DataMode): void
  editV4SensitiveTerms(text: string): void
  editV4Classifier(enabled: boolean, modelId?: string): void
  upsertV4Row(collection: V4CollectionKey, value: Row, previousId?: string): void
  removeV4Row(collection: V4CollectionKey, id: string): void
}

const ROLE_KEYS = ['planner', 'worker', 'judge', 'classifier'] as const
const DEPLOYMENTS = ['external-cloud', 'trusted-cloud', 'local', 'simulated-local'] as const
const PROVIDER_TYPES = ['openai-compatible', 'openai-responses', 'ark-agent-plan', 'dsh'] as const

function records(value: unknown): Row[] {
  return Array.isArray(value) ? value.filter((row): row is Row => row !== null && typeof row === 'object' && !Array.isArray(row)) : []
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function numberValue(value: unknown): string | number {
  return typeof value === 'number' && Number.isFinite(value) ? value : ''
}

function numberDraft(value: string): number | undefined {
  if (value.trim() === '') return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function without(row: Row, ...keys: string[]): Row {
  const next = { ...row }
  for (const key of keys) delete next[key]
  return next
}

function nextId(prefix: string, rows: Row[]): string {
  let index = rows.length + 1
  while (rows.some(row => row.id === `${prefix}-${index}`)) index += 1
  return `${prefix}-${index}`
}

export function V4Settings(props: V4SettingsProps) {
  const { t, provider, disabled } = props
  const objective = provider.objective ?? {}
  const security = provider.security ?? {}
  const classifier = security.classifier !== null && typeof security.classifier === 'object'
    && !Array.isArray(security.classifier) ? security.classifier as Row : {}
  const policies = records(provider.trustPolicies)
  const providers = records(provider.providers)
  const models = records(provider.models)
  const preview = buildV4FeasibilityPreview(provider)!
  const classifierModels = models.filter(model => Array.isArray(model.roles) && model.roles.includes('classifier'))

  const update = (collection: V4CollectionKey, row: Row, patch: Row) => {
    props.upsertV4Row(collection, { ...row, ...patch }, stringValue(row.id))
  }
  const replace = (collection: V4CollectionKey, row: Row, next: Row) => {
    props.upsertV4Row(collection, next, stringValue(row.id))
  }
  const textInput = (label: string, value: unknown, onChange: (value: string) => void, placeholder = '') => (
    <label className="rra-compact-field">
      <span className="rra-label">{label}</span>
      <input className="rra-input" value={stringValue(value)} placeholder={placeholder} disabled={disabled}
        onChange={event => onChange(event.target.value)} />
    </label>
  )
  const numberInput = (label: string, value: unknown, onChange: (value: number | undefined) => void,
    options: { min?: number; max?: number; step?: string } = {}) => (
    <label className="rra-compact-field">
      <span className="rra-label">{label}</span>
      <input className="rra-input" type="number" value={numberValue(value)} min={options.min} max={options.max}
        step={options.step ?? '1'} disabled={disabled} onChange={event => onChange(numberDraft(event.target.value))} />
    </label>
  )

  if (!props.advanced) return <section className="rra-v4-section rra-simple" aria-label={t('v4SimpleTitle')}>
    <div className="rra-section-head">
      <div><h3>{t('v4SimpleTitle')}</h3><p className="rra-field-hint">{t('v4SimpleHint')}</p></div>
      <span className={'rra-status ' + (preview.missingRoles.length ? 'rra-status-bad' : '')}>
        {preview.missingRoles.length ? t('v4ConfigIncomplete') : t('v4ConfigReady')}
      </span>
    </div>
    <div className="rra-simple-status">
      <strong>{t('v4AutomaticEnabled')}</strong>
      <span>{preview.modelCount} {t('v4ModelsAvailable')} · {preview.providerCount} {t('v4ProvidersAvailable')}</span>
      <span>{preview.hasLocalDeployment ? t('v4LocalAvailable') : t('v4ExternalOnly')}</span>
    </div>
    <div className="rra-grid rra-grid-2">
      {numberInput(t('v4QualityMin'), objective.qualityMin,
        value => value !== undefined && props.editV4QualityMin(value), { min: 0, max: 100 })}
      <label className="rra-compact-field">
        <span className="rra-label">{t('v4DataMode')}</span>
        <select className="rra-select" value={stringValue(security.dataMode) || 'live'} disabled={disabled}
          onChange={event => props.editV4DataMode(event.target.value as V4DataMode)}>
          <option value="live">{t('v4DataLive')}</option>
          <option value="desensitized">{t('v4DataDesensitized')}</option>
          <option value="synthetic">{t('v4DataSynthetic')}</option>
        </select>
      </label>
    </div>
    <p className="rra-field-hint">{t('v4SimpleBoundaryHint')}</p>
  </section>

  return <>
    <section className="rra-v4-section" aria-label={t('v4Objective')}>
      <div className="rra-section-head">
        <div><h3>{t('v4Objective')}</h3><p className="rra-field-hint">{t('v4ObjectiveHint')}</p></div>
        <span className="rra-badge">cost → latency</span>
      </div>
      <div className="rra-grid rra-grid-2">
        {numberInput(t('v4QualityMin'), objective.qualityMin,
          value => value !== undefined && props.editV4QualityMin(value), { min: 0, max: 100 })}
        <label className="rra-compact-field">
          <span className="rra-label">{t('v4DagMode')}</span>
          <select className="rra-select" value={stringValue(objective.dagMode) || 'auto'} disabled={disabled}
            onChange={event => props.editV4DagMode(event.target.value as V4DagMode)}>
            <option value="auto">{t('v4DagAuto')}</option>
            <option value="never">{t('v4DagNever')}</option>
            <option value="force">{t('v4DagForce')}</option>
          </select>
        </label>
      </div>
      <p className="rra-field-hint">{t('v4BudgetHint')}</p>
    </section>

    <section className="rra-v4-section" aria-label={t('v4Security')}>
      <div className="rra-section-head">
        <div><h3>{t('v4Security')}</h3><p className="rra-field-hint">{t('v4SecurityHint')}</p></div>
      </div>
      <div className="rra-grid rra-grid-2">
        <label className="rra-compact-field">
          <span className="rra-label">{t('v4DataMode')}</span>
          <select className="rra-select" value={stringValue(security.dataMode) || 'live'} disabled={disabled}
            onChange={event => props.editV4DataMode(event.target.value as V4DataMode)}>
            <option value="live">{t('v4DataLive')}</option>
            <option value="desensitized">{t('v4DataDesensitized')}</option>
            <option value="synthetic">{t('v4DataSynthetic')}</option>
          </select>
        </label>
        <label className="rra-compact-field">
          <span className="rra-label">{t('v4Classifier')}</span>
          <select className="rra-select" value={stringValue(classifier.modelId)} disabled={disabled}
            onChange={event => props.editV4Classifier(event.target.value !== '', event.target.value)}>
            <option value="">{t('v4ClassifierDisabled')}</option>
            {classifierModels.map(model => <option key={stringValue(model.id)} value={stringValue(model.id)}>
              {stringValue(model.id)} · {stringValue(model.model)}
            </option>)}
          </select>
        </label>
      </div>
      <label className="rra-compact-field">
        <span className="rra-label">{t('v4SensitiveTerms')}</span>
        <textarea className="rra-textarea" rows={3} disabled={disabled}
          value={(Array.isArray(security.sensitiveTerms) ? security.sensitiveTerms : []).filter(term => typeof term === 'string').join('\n')}
          placeholder={t('v4SensitiveTermsPlaceholder')}
          onChange={event => props.editV4SensitiveTerms(event.target.value)} />
      </label>
    </section>

    <section className="rra-v4-section" aria-label={t('v4Feasibility')}>
      <div className="rra-section-head">
        <div><h3>{t('v4Feasibility')}</h3><p className="rra-field-hint">{t('v4FeasibilityHint')}</p></div>
        <span className={'rra-status ' + (preview.missingRoles.length ? 'rra-status-bad' : 'rra-status-warn')}>
          {preview.missingRoles.length ? t('v4StructureBlocked') : t('v4CoreValidationPending')}
        </span>
      </div>
      <div className="rra-preview-grid">
        {ROLE_KEYS.map(role => <div className="rra-preview-cell" key={role}>
          <span>{t('v4Role_' + role)}</span><strong>{preview.roleCounts[role]}</strong>
        </div>)}
      </div>
      <div className="rra-scenarios">
        <div><strong>{t('v4ScenarioPublic')}</strong><span>{preview.missingRoles.length ? t('v4MissingRoles') + preview.missingRoles.join(', ') : t('v4CoreValidationPending')}</span></div>
        <div><strong>{t('v4ScenarioSensitive')}</strong><span>{t('v4SensitiveNeedsCore')}</span></div>
        <div><strong>{t('v4ScenarioNoLocal')}</strong><span>{preview.hasLocalDeployment ? t('v4LocalDeclared') : t('v4NoLocalDeclared')}</span></div>
      </div>
      <p className="rra-field-hint">{t('v4Inventory')}: {preview.providerCount} providers · {preview.modelCount} models · {preview.trustPolicyCount} policies</p>
    </section>

    <section className="rra-v4-section" aria-label={t('v4TrustPolicies')}>
      <div className="rra-section-head">
        <div><h3>{t('v4TrustPolicies')}</h3><p className="rra-field-hint">{t('v4TrustPoliciesHint')}</p></div>
        <button type="button" className="rra-button rra-button-secondary" disabled={disabled}
          onClick={() => props.upsertV4Row('trustPolicies', { id: nextId('trust', policies), residency: '',
            auditLogging: false, allowsSensitiveData: false })}>{t('v4AddPolicy')}</button>
      </div>
      {policies.map((row, index) => <div className="rra-row-card" key={`${stringValue(row.id)}-${index}`}>
        <div className="rra-row-title"><strong>{stringValue(row.id) || t('v4UntitledPolicy')}</strong>
          <button className="rra-reset" type="button" disabled={disabled}
            onClick={() => props.removeV4Row('trustPolicies', stringValue(row.id))}>{t('v4Remove')}</button></div>
        <div className="rra-grid rra-grid-3">
          {textInput(t('v4Id'), row.id, value => update('trustPolicies', row, { id: value }))}
          {textInput(t('v4Residency'), row.residency, value => update('trustPolicies', row, { residency: value }), 'CN / EU / US')}
          {textInput(t('v4ExpiresOn'), row.expiresOn, value => replace('trustPolicies', row,
            value ? { ...row, expiresOn: value } : without(row, 'expiresOn')))}
        </div>
        <div className="rra-check-row">
          {([['auditLogging', 'v4AuditLogging'], ['allowsSensitiveData', 'v4AllowsSensitive'],
            ['acknowledgeExternalTransmission', 'v4ExternalAck']] as const).map(([field, label]) =>
            <label className="rra-check" key={field}><input type="checkbox" disabled={disabled}
              checked={row[field] === true} onChange={event => update('trustPolicies', row, { [field]: event.target.checked })} />
              <span>{t(label)}</span></label>)}
        </div>
      </div>)}
      {policies.length === 0 ? <p className="rra-empty">{t('v4NoPolicies')}</p> : null}
    </section>

    <section className="rra-v4-section" aria-label={t('v4Providers')}>
      <div className="rra-section-head">
        <div><h3>{t('v4Providers')}</h3><p className="rra-field-hint">{t('v4ProvidersHint')}</p></div>
        <button type="button" className="rra-button rra-button-secondary" disabled={disabled}
          onClick={() => props.upsertV4Row('providers', { id: nextId('provider', providers),
            type: 'openai-compatible', deployment: 'external-cloud', baseUrl: 'https://', credentialEnv: '' })}>
          {t('v4AddProvider')}</button>
      </div>
      {providers.map((row, index) => {
        const id = stringValue(row.id)
        const type = stringValue(row.type) || 'openai-compatible'
        return <div className="rra-row-card" key={`${id}-${index}`}>
          <div className="rra-row-title"><strong>{id || t('v4UntitledProvider')}</strong>
            <button className="rra-reset" type="button" disabled={disabled}
              onClick={() => props.removeV4Row('providers', id)}>{t('v4Remove')}</button></div>
          <div className="rra-grid rra-grid-3">
            {textInput(t('v4Id'), row.id, value => update('providers', row, { id: value }))}
            <label className="rra-compact-field"><span className="rra-label">{t('v4ProviderType')}</span>
              <select className="rra-select" value={type} disabled={disabled} onChange={event => {
                const nextType = event.target.value
                const cleaned = nextType === 'dsh' ? without(row, 'baseUrl', 'credentialEnv', 'maxTokensParameter') : without(row, 'dshProvider')
                props.upsertV4Row('providers', { ...cleaned, type: nextType }, id)
              }}>{PROVIDER_TYPES.map(value => <option key={value}>{value}</option>)}</select>
            </label>
            <label className="rra-compact-field"><span className="rra-label">{t('v4Deployment')}</span>
              <select className="rra-select" value={stringValue(row.deployment)} disabled={disabled}
                onChange={event => update('providers', row, { deployment: event.target.value })}>
                {DEPLOYMENTS.map(value => <option key={value}>{value}</option>)}
              </select>
            </label>
            {type === 'dsh'
              ? textInput(t('v4DshProvider'), row.dshProvider, value => update('providers', row, { dshProvider: value }))
              : <>{textInput(t('v4BaseUrl'), row.baseUrl, value => update('providers', row, { baseUrl: value }))}
                {textInput(t('v4CredentialEnv'), row.credentialEnv, value => update('providers', row, { credentialEnv: value }), 'TEAM_MODEL_KEY')}</>}
            {(row.deployment === 'trusted-cloud' || row.deployment === 'simulated-local')
              ? <label className="rra-compact-field"><span className="rra-label">{t('v4TrustPolicy')}</span>
                <select className="rra-select" value={stringValue(row.trustPolicy)} disabled={disabled}
                  onChange={event => replace('providers', row, event.target.value
                    ? { ...row, trustPolicy: event.target.value } : without(row, 'trustPolicy'))}>
                  <option value="">{t('v4SelectPolicy')}</option>
                  {policies.map(policy => <option key={stringValue(policy.id)} value={stringValue(policy.id)}>{stringValue(policy.id)}</option>)}
                </select></label> : null}
          </div>
        </div>
      })}
    </section>

    <section className="rra-v4-section" aria-label={t('v4Models')}>
      <div className="rra-section-head">
        <div><h3>{t('v4Models')}</h3><p className="rra-field-hint">{t('v4ModelsHint')}</p></div>
        <button type="button" className="rra-button rra-button-secondary" disabled={disabled || providers.length === 0}
          onClick={() => props.upsertV4Row('models', { id: nextId('model', models), provider: stringValue(providers[0]?.id),
            model: '', roles: ['worker'], contextWindow: 131072, maxOutputTokens: 4096,
            pricing: { unit: stringValue(provider.billingUnit) || 'USD', inputPer1k: 0, outputPer1k: 0 },
            routing: { quality: 80, latencyMs: 10000 } })}>{t('v4AddModel')}</button>
      </div>
      {models.map((row, index) => {
        const id = stringValue(row.id)
        const pricing = row.pricing !== null && typeof row.pricing === 'object' && !Array.isArray(row.pricing) ? row.pricing as Row : {}
        const routing = row.routing !== null && typeof row.routing === 'object' && !Array.isArray(row.routing) ? row.routing as Row : {}
        const roles = Array.isArray(row.roles) ? row.roles.filter(role => typeof role === 'string') as string[] : []
        const patchNested = (field: 'pricing' | 'routing', current: Row, key: string, value: unknown) =>
          update('models', row, { [field]: value === undefined ? without(current, key) : { ...current, [key]: value } })
        return <div className="rra-row-card" key={`${id}-${index}`}>
          <div className="rra-row-title"><strong>{id || t('v4UntitledModel')}</strong>
            <button className="rra-reset" type="button" disabled={disabled}
              onClick={() => props.removeV4Row('models', id)}>{t('v4Remove')}</button></div>
          <div className="rra-grid rra-grid-3">
            {textInput(t('v4Id'), row.id, value => update('models', row, { id: value }))}
            <label className="rra-compact-field"><span className="rra-label">{t('v4ProviderRef')}</span>
              <select className="rra-select" value={stringValue(row.provider)} disabled={disabled}
                onChange={event => update('models', row, { provider: event.target.value })}>
                {providers.map(item => <option key={stringValue(item.id)} value={stringValue(item.id)}>{stringValue(item.id)}</option>)}
              </select></label>
            {textInput(t('v4ApiModel'), row.model, value => update('models', row, { model: value }))}
            {numberInput(t('v4ContextWindow'), row.contextWindow, value => replace('models', row,
              value === undefined ? without(row, 'contextWindow') : { ...row, contextWindow: value }))}
            {numberInput(t('v4MaxOutput'), row.maxOutputTokens, value => replace('models', row,
              value === undefined ? without(row, 'maxOutputTokens') : { ...row, maxOutputTokens: value }))}
            {textInput(t('v4ReasoningEffort'), row.reasoningEffort, value => replace('models', row,
              value ? { ...row, reasoningEffort: value } : without(row, 'reasoningEffort')))}
          </div>
          <fieldset className="rra-role-grid" disabled={disabled}><legend className="rra-label">{t('v4Roles')}</legend>
            {ROLE_KEYS.map(role => <label className="rra-check" key={role}><input type="checkbox" checked={roles.includes(role)}
              onChange={event => update('models', row, { roles: event.target.checked
                ? [...new Set([...roles, role])] : roles.filter(value => value !== role) })} />
              <span>{t('v4Role_' + role)}</span></label>)}
          </fieldset>
          <div className="rra-grid rra-grid-3">
            {numberInput(t('v4InputPrice'), pricing.inputPer1k, value => patchNested('pricing', pricing, 'inputPer1k', value), { min: 0, step: '0.0001' })}
            {numberInput(t('v4CachedPrice'), pricing.cachedInputPer1k, value => patchNested('pricing', pricing, 'cachedInputPer1k', value), { min: 0, step: '0.0001' })}
            {numberInput(t('v4OutputPrice'), pricing.outputPer1k, value => patchNested('pricing', pricing, 'outputPer1k', value), { min: 0, step: '0.0001' })}
            {roles.includes('worker') ? <>
              {numberInput(t('v4QualityPrediction'), routing.quality, value => patchNested('routing', routing, 'quality', value), { min: 0, max: 100 })}
              {numberInput(t('v4LatencyPrediction'), routing.latencyMs, value => patchNested('routing', routing, 'latencyMs', value), { min: 0 })}
            </> : null}
          </div>
        </div>
      })}
      {models.length === 0 ? <p className="rra-empty">{t('v4NoModelsConfigured')}</p> : null}
    </section>
  </>
}
