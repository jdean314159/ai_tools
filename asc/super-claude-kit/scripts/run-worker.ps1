param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Profile,
  [Parameter(Position = 1)]
  [string]$SessionId,
  [Parameter(Position = 2)]
  [string]$AgentMailProjectKey,
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ClaudeArgs
)

function New-SessionId {
  param([string]$ProfileName)
  $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $suffix = Get-Random -Maximum 100000
  return "{0}-{1}-{2}" -f $ProfileName, $timestamp, $suffix
}

if (-not $SessionId) {
  $SessionId = New-SessionId -ProfileName $Profile
}

if ($AgentMailProjectKey) {
  $env:CLAUDE_AGENT_MAIL_PROJECT_KEY = $AgentMailProjectKey
}

$env:CLAUDE_WORKER_PROFILE = $Profile
$env:CLAUDE_SESSION_ID = $SessionId

$requiredEntries = @(
  'CLAUDE_WORKER_PROFILE/u',
  'CLAUDE_SESSION_ID/u',
  'CLAUDE_AGENT_MAIL_PROJECT_KEY/u'
)

$existing = @()
if ($env:WSLENV) {
  $existing = $env:WSLENV -split ':' | Where-Object { $_ }
}

foreach ($entry in $requiredEntries) {
  if (-not ($existing -contains $entry)) {
    $existing += $entry
  }
}

$env:WSLENV = ($existing | Where-Object { $_ } | Select-Object -Unique) -join ':'

Write-Host ("Launching Claude with worker '{0}' (session: {1})" -f $Profile, $SessionId)
if ($AgentMailProjectKey) {
  Write-Host ("  Agent Mail project: {0}" -f $AgentMailProjectKey)
}

& claude @ClaudeArgs
