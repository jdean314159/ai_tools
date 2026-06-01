<#
.SYNOPSIS
    Interactive worker selection for Super Claude Kit
.DESCRIPTION
    Prompts user to select a worker profile, then launches Claude with the appropriate
    environment variables set. Supports parallel workers in different terminal windows.
    Sets the terminal tab title to the worker's preferred_name.
.EXAMPLE
    select-worker
    # Shows interactive menu, then launches claude
.EXAMPLE
    select-worker -List
    # Just lists available workers without launching
#>

param(
    [Parameter(Position = 0)]
    [string]$QuickSelect,

    [switch]$List,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClaudeArgs
)

$WorkersDir = ".claude\workers"
$GlobalWorkersDir = "$env:USERPROFILE\.claude\workers"

function Get-WorkerIdentity {
    param([string]$FilePath)

    $identity = @{
        preferred_name = $null
        mailbox = $null
        register_with_agent_mail = $false
        uses_beads = $false
    }

    if (-not (Test-Path $FilePath)) {
        return $identity
    }

    $content = Get-Content $FilePath -Raw

    # Check if file has YAML frontmatter
    if ($content -match '^---\s*\r?\n([\s\S]*?)\r?\n---') {
        $frontmatter = $Matches[1]

        # Parse worker-identity block
        if ($frontmatter -match 'worker-identity:\s*\r?\n((?:\s+[^\r\n]+\r?\n?)*)') {
            $identityBlock = $Matches[1]

            if ($identityBlock -match 'preferred_name:\s*(\S+)') {
                $identity.preferred_name = $Matches[1]
            }
            if ($identityBlock -match 'mailbox:\s*(\S+)') {
                $identity.mailbox = $Matches[1]
            }
            if ($identityBlock -match 'register_with_agent_mail:\s*(true|yes)') {
                $identity.register_with_agent_mail = $true
            }
            if ($identityBlock -match 'uses_beads:\s*(true|yes)') {
                $identity.uses_beads = $true
            }
        }

        # Also check top-level preferred_name (some formats)
        if (-not $identity.preferred_name -and $frontmatter -match '^\s*preferred_name:\s*(\S+)') {
            $identity.preferred_name = $Matches[1]
        }
    }

    return $identity
}

function Get-AvailableWorkers {
    $workers = @()

    # Check local project workers first
    if (Test-Path $WorkersDir) {
        Get-ChildItem -Path $WorkersDir -Filter "*.md" -File | ForEach-Object {
            if ($_.Name -ne "README.md") {
                $identity = Get-WorkerIdentity -FilePath $_.FullName
                $workers += @{
                    Name = $_.BaseName
                    Path = $_.FullName
                    Source = "project"
                    PreferredName = if ($identity.preferred_name) { $identity.preferred_name } else { $_.BaseName }
                    Identity = $identity
                }
            }
        }
        # Also check subdirectories (worker/role.md pattern)
        Get-ChildItem -Path $WorkersDir -Directory | ForEach-Object {
            $roleFile = Join-Path $_.FullName "role.md"
            $configFile = Join-Path $_.FullName "config.md"
            $workerFile = $null

            if (Test-Path $roleFile) {
                $workerFile = $roleFile
            } elseif (Test-Path $configFile) {
                $workerFile = $configFile
            }

            if ($workerFile) {
                $identity = Get-WorkerIdentity -FilePath $workerFile
                $workers += @{
                    Name = $_.Name
                    Path = $workerFile
                    Source = "project"
                    PreferredName = if ($identity.preferred_name) { $identity.preferred_name } else { $_.Name }
                    Identity = $identity
                }
            }
        }
    }

    # Check global workers
    if (Test-Path $GlobalWorkersDir) {
        Get-ChildItem -Path $GlobalWorkersDir -Filter "*.md" -File | ForEach-Object {
            if ($_.Name -ne "README.md") {
                $existingNames = $workers | ForEach-Object { $_.Name }
                if ($_.BaseName -notin $existingNames) {
                    $identity = Get-WorkerIdentity -FilePath $_.FullName
                    $workers += @{
                        Name = $_.BaseName
                        Path = $_.FullName
                        Source = "global"
                        PreferredName = if ($identity.preferred_name) { $identity.preferred_name } else { $_.BaseName }
                        Identity = $identity
                    }
                }
            }
        }
    }

    return $workers | Sort-Object { $_.Name }
}

function Show-WorkerMenu {
    param([array]$Workers)

    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host "  Super Claude Kit - Worker Selection" -ForegroundColor Cyan
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""

    $i = 1
    foreach ($worker in $Workers) {
        $sourceTag = if ($worker.Source -eq "global") { " (global)" } else { "" }
        $displayName = $worker.Name
        if ($worker.PreferredName -and $worker.PreferredName -ne $worker.Name) {
            $displayName = "$($worker.Name) -> $($worker.PreferredName)"
        }
        Write-Host "  [$i] $displayName$sourceTag" -ForegroundColor White
        $i++
    }

    Write-Host ""
    Write-Host "  [0] Default (no specific worker)" -ForegroundColor DarkGray
    Write-Host "  [q] Quit" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
    Write-Host ""
}

function New-SessionId {
    param([string]$ProfileName)
    $timestamp = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $suffix = Get-Random -Maximum 100000
    return "{0}-{1}-{2}" -f $ProfileName, $timestamp, $suffix
}

function Set-TerminalTitle {
    param([string]$Title)

    # Set console window title
    $Host.UI.RawUI.WindowTitle = $Title

    # Also try to set Windows Terminal tab title (if running in WT)
    if ($env:WT_SESSION) {
        # Windows Terminal supports OSC 9;9 for tab title
        Write-Host "`e]9;9;$Title`e\" -NoNewline
    }

    # Set using ANSI escape sequence (works in most modern terminals)
    Write-Host "`e]0;$Title`a" -NoNewline
}

function Get-TempPrefix {
    param([hashtable]$Worker)

    # Use mailbox if available, otherwise profile name
    $base = if ($Worker.Identity.mailbox) { $Worker.Identity.mailbox } else { $Worker.Name }
    # Slugify: lowercase, replace non-alphanumeric with underscore
    $slug = ($base -replace '[^a-zA-Z0-9]', '_').ToLower().Trim('_')
    if (-not $slug) { $slug = "worker" }
    return $slug
}

function Start-WorkerSession {
    param(
        [hashtable]$Worker,
        [string[]]$ExtraArgs
    )

    $env:CLAUDE_WORKER_PROFILE = $Worker.Name
    $env:CLAUDE_SESSION_ID = New-SessionId -ProfileName $Worker.Name

    # Set session directory path
    $env:CLAUDE_SESSION_DIR = ".claude/sessions/$($env:CLAUDE_SESSION_ID)"

    # Set temp file prefix for this worker
    $env:CLAUDE_WORKER_TEMP_PREFIX = Get-TempPrefix -Worker $Worker

    # Set terminal title to preferred name and store in env var for hooks to use
    $title = $Worker.PreferredName
    if (-not $title) { $title = $Worker.Name }
    $env:CLAUDE_TERMINAL_TITLE = $title
    Set-TerminalTitle -Title $title

    Write-Host ""
    Write-Host "Launching Claude with worker: $($Worker.Name)" -ForegroundColor Green
    Write-Host "Session ID: $env:CLAUDE_SESSION_ID" -ForegroundColor DarkGray
    Write-Host "Session Dir: $env:CLAUDE_SESSION_DIR" -ForegroundColor DarkGray
    Write-Host "Temp Prefix: $env:CLAUDE_WORKER_TEMP_PREFIX" -ForegroundColor DarkGray
    Write-Host ""

    # Set up WSLENV for bash hooks
    $requiredEntries = @(
        'CLAUDE_WORKER_PROFILE/u',
        'CLAUDE_SESSION_ID/u',
        'CLAUDE_SESSION_DIR/u',
        'CLAUDE_WORKER_TEMP_PREFIX/u',
        'CLAUDE_TERMINAL_TITLE/u'
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

    & claude @ExtraArgs

    # Restore title after Claude exits (in case it was changed)
    Set-TerminalTitle -Title $title
}

# Get available workers
$workers = Get-AvailableWorkers

if ($workers.Count -eq 0) {
    Write-Host "No worker profiles found." -ForegroundColor Yellow
    Write-Host "Create workers in .claude/workers/ or ~/.claude/workers/" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Launching Claude with default profile..." -ForegroundColor Cyan
    Set-TerminalTitle -Title "Claude (default)"
    & claude @ClaudeArgs
    exit
}

# List mode - just show workers and exit
if ($List) {
    Write-Host ""
    Write-Host "Available Workers:" -ForegroundColor Cyan
    Write-Host ""
    foreach ($worker in $workers) {
        $sourceTag = if ($worker.Source -eq "global") { " (global)" } else { "" }
        $nameDisplay = $worker.Name
        if ($worker.PreferredName -and $worker.PreferredName -ne $worker.Name) {
            $nameDisplay = "$($worker.Name) (title: $($worker.PreferredName))"
        }
        Write-Host "  - $nameDisplay$sourceTag"
    }
    Write-Host ""
    exit
}

# Quick select mode - match by name or number
if ($QuickSelect) {
    $selected = $null

    # Try as number first
    if ($QuickSelect -match '^\d+$') {
        $index = [int]$QuickSelect - 1
        if ($index -ge 0 -and $index -lt $workers.Count) {
            $selected = $workers[$index]
        }
    }

    # Try as name (partial match)
    if (-not $selected) {
        $selected = $workers | Where-Object { $_.Name -like "*$QuickSelect*" } | Select-Object -First 1
    }

    if ($selected) {
        Start-WorkerSession -Worker $selected -ExtraArgs $ClaudeArgs
        exit
    } else {
        Write-Host "No worker found matching: $QuickSelect" -ForegroundColor Red
        Write-Host ""
    }
}

# Interactive menu
Show-WorkerMenu -Workers $workers

$selection = Read-Host "Select worker"

switch ($selection) {
    "q" {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit
    }
    "0" {
        Write-Host "Launching Claude with default profile..." -ForegroundColor Cyan
        Set-TerminalTitle -Title "Claude (default)"
        & claude @ClaudeArgs
        exit
    }
    default {
        if ($selection -match '^\d+$') {
            $index = [int]$selection - 1
            if ($index -ge 0 -and $index -lt $workers.Count) {
                $selected = $workers[$index]
                Start-WorkerSession -Worker $selected -ExtraArgs $ClaudeArgs
                exit
            }
        }

        Write-Host "Invalid selection: $selection" -ForegroundColor Red
        exit 1
    }
}
