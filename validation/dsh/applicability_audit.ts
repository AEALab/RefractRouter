// 仅生成本机通信诊断；不记录请求正文、凭证容器或任意响应字段。
export function hostDiagnostic(request: Record<string, any>, response: Record<string, any>,
  secrets: Record<string, unknown>, elapsedMs: number): Record<string, unknown> {
  const redact = (value: unknown): string => {
    let text = String(value ?? '')
    for (const secret of Object.values(secrets)) {
      if (typeof secret === 'string' && secret.length) text = text.replaceAll(secret, '[凭证已隐去]')
    }
    return text.replace(/\b(?:apikey_|sk-(?:or-v1-)?)[A-Za-z0-9_-]+/g, '[凭证已隐去]')
      .replace(/Bearer\s+\S+/gi, 'Bearer [凭证已隐去]')
      .replace(/((?:api[_-]?key|authorization)\s*[=:]\s*)[^\s,;]+/gi, '$1[凭证已隐去]')
      .slice(0, 300)
  }
  return {
    schemaVersion: 'automatic-host-diagnostic-v1', id: redact(request.id),
    provider: redact(request.provider), model: redact(request.model), ok: response.ok === true,
    elapsedMs: Math.max(0, Math.round(elapsedMs)),
    ...(response.ok === true ? {} : {failureType: redact(response.failure_type),
      message: redact(response.message), requestId: redact(response.request_id)}),
  }
}
