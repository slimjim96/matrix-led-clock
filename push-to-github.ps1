param(
    [string]$Message = "",
    [string]$Branch = "",
    [string]$Remote = "origin",
    [string]$RemoteUrl = "https://github.com/slimjim96/matrix-led-clock.git",
    [switch]$CommitOnly
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Get-GitOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Args
    )

    $output = & git @Args 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($output | Out-String).Trim()
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
    throw "No .git directory found in $repoRoot. Initialize the repository first."
}

$safeDirectory = ($repoRoot -replace "\\", "/")
Invoke-Git -Args @("config", "--global", "--add", "safe.directory", $safeDirectory)

if ([string]::IsNullOrWhiteSpace($Message)) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $Message = "Update CircuitPython files ($timestamp)"
}

$currentBranch = Get-GitOutput -Args @("-c", "safe.directory=$safeDirectory", "branch", "--show-current")
if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    if ([string]::IsNullOrWhiteSpace($Branch)) {
        $Branch = "main"
    }
    Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "checkout", "-b", $Branch)
    $currentBranch = $Branch
} elseif (-not [string]::IsNullOrWhiteSpace($Branch) -and $Branch -ne $currentBranch) {
    Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "checkout", $Branch)
    $currentBranch = $Branch
}

$remoteName = Get-GitOutput -Args @("-c", "safe.directory=$safeDirectory", "remote", "get-url", $Remote)
if ([string]::IsNullOrWhiteSpace($remoteName) -and -not [string]::IsNullOrWhiteSpace($RemoteUrl)) {
    Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "remote", "add", $Remote, $RemoteUrl)
    $remoteName = $RemoteUrl
} elseif (-not [string]::IsNullOrWhiteSpace($remoteName) -and -not [string]::IsNullOrWhiteSpace($RemoteUrl) -and $remoteName -ne $RemoteUrl) {
    Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "remote", "set-url", $Remote, $RemoteUrl)
    $remoteName = $RemoteUrl
}

Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "add", "-A")

$status = Get-GitOutput -Args @("-c", "safe.directory=$safeDirectory", "status", "--short")
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "No changes to commit."
    exit 0
}

Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "commit", "-m", $Message)

if ($CommitOnly) {
    Write-Host "Committed locally on branch '$currentBranch'."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($remoteName)) {
    throw "No remote named '$Remote' is configured. Re-run with -RemoteUrl <repo-url>."
}

Invoke-Git -Args @("-c", "safe.directory=$safeDirectory", "push", "-u", $Remote, $currentBranch)
Write-Host "Pushed '$currentBranch' to '$Remote'."
