param(
    [Parameter(Mandatory=$true)][string]$Gh,
    [string]$Repository = 'pythonofGVR/japanese_offline_translator',
    [string]$Tag = 'v1.1.0'
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$assets = Join-Path $project 'dist/release-v1.1.0'
$notes = Join-Path $project 'reports/v1.1-release-notes.md'
$branch = & git -c "safe.directory=$($project.Replace('\','/'))" -C $project branch --show-current
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine task branch.' }
& $Gh release view $Tag --repo $Repository --json id 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) { throw 'Release already exists; refusing to overwrite another release.' }
& $Gh release create $Tag --repo $Repository --target $branch.Trim() --draft --title 'Japanese Offline Translator v1.1.0' --notes-file $notes
if ($LASTEXITCODE -ne 0) { throw 'Draft creation failed.' }
foreach ($file in Get-ChildItem -LiteralPath $assets -File | Sort-Object Name) {
    if ($file.Length -ge 2GB) { throw "Asset exceeds GitHub limit: $($file.Name)" }
    $success = $false
    for ($attempt=1; $attempt -le 3; $attempt++) {
        Write-Output "Uploading $($file.Name) (attempt $attempt)"
        & $Gh release upload $Tag $file.FullName --repo $Repository --clobber
        if ($LASTEXITCODE -eq 0) { $success=$true; break }
    }
    if (!$success) { throw "Upload failed: $($file.Name). Draft retained for recovery." }
}
$download = Join-Path $project 'downloads/github-v1.1-verify'
New-Item -ItemType Directory -Force -Path $download | Out-Null
& $Gh release download $Tag --repo $Repository --dir $download --clobber
if ($LASTEXITCODE -ne 0) { throw 'Download verification failed. Draft not published.' }
foreach ($line in Get-Content -LiteralPath (Join-Path $download 'SHA256SUMS.txt') -Encoding UTF8) {
    if (!$line) { continue }
    $parts = $line -split '  ',2
    $local = Join-Path $assets $parts[1]
    $received = Join-Path $download $parts[1]
    $expected = (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash
    $actual = (Get-FileHash -LiteralPath $received -Algorithm SHA256).Hash
    if ($expected -ine $parts[0] -or $actual -ine $expected) { throw "Downloaded hash mismatch: $($parts[1])" }
    Write-Output "Verified $($parts[1])"
}
Write-Output 'DRAFT UPLOAD AND DOWNLOAD HASH VERIFICATION PASS. Publish only after downloaded installer verification.'
