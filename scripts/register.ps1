param(
    [string]$SkillsRoot = $(
        if ($env:CODEX_HOME) {
            Join-Path $env:CODEX_HOME 'skills'
        } else {
            Join-Path $env:USERPROFILE '.codex\skills'
        }
    )
)

$ErrorActionPreference = 'Stop'
$SkillRoot = (Split-Path -Parent $PSScriptRoot).TrimEnd('\')
$Link = Join-Path $SkillsRoot 'ai-video-edit-platform'

if (-not (Test-Path -LiteralPath (Join-Path $SkillRoot 'SKILL.md'))) {
    throw "Invalid skill root: $SkillRoot"
}
if (-not (Test-Path -LiteralPath $SkillsRoot)) {
    throw "Codex skills directory not found: $SkillsRoot"
}
if (Test-Path -LiteralPath $Link) {
    $item = Get-Item -LiteralPath $Link -Force
    $target = @($item.Target)[0]
    if ($target -and ((Resolve-Path -LiteralPath $target).Path.TrimEnd('\') -eq $SkillRoot)) {
        Write-Output "Already registered: $Link -> $SkillRoot"
        exit 0
    }
    throw "A different skill already exists at $Link"
}

New-Item -ItemType Junction -Path $Link -Target $SkillRoot | Out-Null
Write-Output "Registered: $Link -> $SkillRoot"
