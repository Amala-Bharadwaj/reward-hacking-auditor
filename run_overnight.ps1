# Overnight driver. Keeps the machine awake, refuses to start without enough
# free memory, and logs everything so a failed run can be diagnosed after.
#
#   powershell -ExecutionPolicy Bypass -File run_overnight.ps1

param(
    [string]$Benchmarks = "mbpp",
    [int]$Samples = 10,
    [int]$MinFreeGB = 5
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$free = [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2)
if ($free -lt $MinFreeGB) {
    Write-Host "Only $free GB free. Ollama needs about 5 GB to load the model."
    Write-Host "Close VS Code, Chrome, Edge and Discord, then run this again."
    exit 1
}
Write-Host "Free RAM: $free GB"

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 15
Write-Host "Sleep, hibernate and disk-sleep disabled on AC."

# Fail before the long run rather than six hours into it. OLLAMA_KEEP_ALIVE is
# already 24h in the environment, so no flag is needed here.
Write-Host "Warming the model (first load takes ~30s)..."
$warm = python -c "from openai import OpenAI; c=OpenAI(base_url='http://localhost:11434/v1',api_key='ollama'); print(c.chat.completions.create(model='qwen2.5-coder:7b',messages=[{'role':'user','content':'ok'}],max_tokens=5).choices[0].message.content)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Model failed to load. Not starting."
    Write-Host $warm
    powercfg /change standby-timeout-ac 30
    exit 1
}
Write-Host "Model loaded."

$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$log = "results/run-$stamp.log"
New-Item -ItemType Directory -Force results | Out-Null
Write-Host "Logging to $log"
Write-Host "Started $(Get-Date -Format 'HH:mm')  --  safe to leave; resume is automatic if interrupted."

python -u llm_attack.py --benchmarks $Benchmarks --samples $Samples 2>&1 |
    Tee-Object -FilePath $log

Write-Host "Finished $(Get-Date -Format 'HH:mm')"
powercfg /change standby-timeout-ac 30
powercfg /change hibernate-timeout-ac 60
