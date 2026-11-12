$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$name = '0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch'
$provenancePath = 'packages/kernel/PATCHES.md'
$seriesPath = 'packages/kernel/patches/series'
$basePath = "packages/kernel/patches/$name"
$driverPath = 'drivers/power/supply/qcom_battmgr.c'
$originalPatch = 'experimental/charge-rate-policy/charge-rate-policy.patch'
$paths = @($provenancePath, $seriesPath, $basePath)
$utf8 = [Text.UTF8Encoding]::new($false)
function Write-Lf([string]$relative, [string]$text) {
    $target = Join-Path $root $relative
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    [IO.File]::WriteAllText($target, $text.Replace("`r`n", "`n"), $utf8)
}
function Get-PatchDiff([string]$before, [string]$after, [string]$path) {
    $lines = & git -c core.safecrlf=false diff --no-index -- $before $after
    if ($LASTEXITCODE -ne 1) { throw "Expected a nonempty diff for $path, exit $LASTEXITCODE" }
    $lines[0] = "diff --git a/$path b/$path"
    for ($index = 1; $index -lt $lines.Count; $index++) {
        if ($lines[$index].StartsWith('@@')) { break }
        if ($lines[$index].StartsWith('--- ') -and $before -ne '/dev/null') { $lines[$index] = "--- a/$path" }
        if ($lines[$index].StartsWith('+++ ')) { $lines[$index] = "+++ b/$path" }
    }
    return ($lines -join "`n") + "`n"
}
$anchor = '0904-power-supply-qcom-battmgr-report-charge-threshold-set-failures.patch'
$series = [IO.File]::ReadAllText((Join-Path $root 'upstream/packages/kernel/patches/series')).Replace("`r`n", "`n")
if (($series.Split(@($anchor), [StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Series anchor must occur exactly once' }
Write-Lf "submission/overlay/$seriesPath" ($series.Replace($anchor, "$anchor`n$name"))
$provenance = [IO.File]::ReadAllText((Join-Path $root 'upstream/packages/kernel/PATCHES.md')).Replace("`r`n", "`n")
$entry = @'
- `patches/0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch`
  source: armada
  upstream: local
  notes: KPFE charge limiting using the firmware charge-rate command and existing threshold controls.
'@
$next = '- `patches/0910-firmware-qcom-scm-allow-QSEECOM-on-OpenABL-s-platforms.patch`'
if (($provenance.Split(@($next), [StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Provenance anchor must occur exactly once' }
$baseProvenance = $provenance.Replace($next, $entry.Replace("`r`n", "`n") + "`n" + $next)
Write-Lf "submission/overlay/$provenancePath" ($baseProvenance.Replace(
    'existing threshold controls.', 'existing threshold controls, with USB-PD renegotiation on eligible awake attachments.'))
$diffs = @()
Push-Location $root
try {
    $kernelDiff = Get-PatchDiff "src/base/$driverPath" 'experimental/usb-pd-reconnect/qcom_battmgr.c' $driverPath
    $header = ([IO.File]::ReadAllText((Join-Path $root $originalPatch)).Replace("`r`n", "`n") -split "`n---`n", 2)[0]
    $pdDescription = @'
On an eligible awake USB-PD attachment during a charge-limit hold,
briefly release the stop to allow higher input voltage negotiation.
Reapply the stop once the voltage rises, the cable is removed, or the
polling deadline expires.
'@
    $adds = ($kernelDiff.Split("`n") | Where-Object { $_ -match '^\+(?!\+\+)' }).Count
    $deletes = ($kernelDiff.Split("`n") | Where-Object { $_ -match '^-(?!--)' }).Count
    Write-Lf "submission/overlay/$basePath" (
        "$header`n$pdDescription`n`n---`n 1 file changed, $adds insertions(+), $deletes deletions(-)`n`n$kernelDiff")
    foreach ($path in $paths) {
        $before = if (Test-Path "upstream/$path") { "upstream/$path" } else { '/dev/null' }
        $diffs += Get-PatchDiff $before "submission/overlay/$path" $path
    }
    Write-Lf 'submission/armada-kpfe-charge-limit.patch' ($diffs -join '')
    $beforeFile = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($beforeFile, $baseProvenance, $utf8)
        $pdDiffs = @(Get-PatchDiff $beforeFile "submission/overlay/$provenancePath" $provenancePath)
        $pdDiffs += Get-PatchDiff $originalPatch "submission/overlay/$basePath" $basePath
        Write-Lf 'submission/armada-kpfe-usb-pd-follow-up.patch' ($pdDiffs -join '')
    } finally { Remove-Item -LiteralPath $beforeFile }
} finally { Pop-Location }
Write-Output 'Prepared the combined Armada diff and the USB-PD follow-up. Run tests/verify_artifacts.py next.'
