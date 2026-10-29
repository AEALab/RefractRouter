/** 已安装核心使用隔离模块搜索路径；不从待分析仓库导入同名模块或用户 sitecustomize。 */
export const CORE_RUNTIME_ENV={PYTHONUNBUFFERED:'1',PYTHONSAFEPATH:'1',PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1'} as const
export function installedCoreCommand(executable:string):string[]{
  const python=/(?:^|\/|\\)python(?:\d+(?:\.\d+)?)?(?:\.exe)?$/i.test(executable)
  return [executable,...(python?['-I','-B','-m','refractrouter.agent_cli']:[])]
}
