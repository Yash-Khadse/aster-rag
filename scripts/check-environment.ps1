$ErrorActionPreference = 'Continue'
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, TotalVisibleMemorySize, FreePhysicalMemory
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Used, Free
foreach ($command in @('uv','python','node','npm','pnpm','docker','ollama','wsl')) {
  Get-Command $command -ErrorAction SilentlyContinue | Select-Object Name, Source
}
