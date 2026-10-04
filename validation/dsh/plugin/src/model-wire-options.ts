/** 提供方传输约束；不参与选模、质量判断或计费。 */
export function modelTemperature(provider: string, model: string, requested: number | undefined): number | undefined {
  // K3 固定 temperature=1；官方建议省略，不传宿主通用的默认 0。
  return provider === 'moonshot' && model === 'kimi-k3' ? undefined : requested
}
