$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$name = '0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch'
$paths = @('packages/kernel/PATCHES.md', 'packages/kernel/patches/series', "packages/kernel/patches/$name")
$utf8 = [Text.UTF8Encoding]::new($false)
function Write-Lf([string]$relative, [string]$text) {
    $target = Join-Path $root $relative
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    [IO.File]::WriteAllText($target, $text.Replace("`r`n", "`n"), $utf8)
}
$anchor = '0904-power-supply-qcom-battmgr-report-charge-threshold-set-failures.patch'
$series = [IO.File]::ReadAllText((Join-Path $root 'upstream/packages/kernel/patches/series')).Replace("`r`n", "`n")
if (($series.Split(@($anchor), [StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Series anchor must occur exactly once' }
Write-Lf 'submission/overlay/packages/kernel/patches/series' ($series.Replace($anchor, "$anchor`n$name"))
$provenance = [IO.File]::ReadAllText((Join-Path $root 'upstream/packages/kernel/PATCHES.md')).Replace("`r`n", "`n")
$entry = @'
- `patches/0905-power-supply-qcom-battmgr-kpfe-charge-rate.patch`
  source: armada
  upstream: local
  notes: KPFE charge limiting using the firmware charge-rate command and existing threshold controls.
'@
$next = '- `patches/0910-firmware-qcom-scm-allow-QSEECOM-on-OpenABL-s-platforms.patch`'
if (($provenance.Split(@($next), [StringSplitOptions]::None).Count - 1) -ne 1) { throw 'Provenance anchor must occur exactly once' }
Write-Lf 'submission/overlay/packages/kernel/PATCHES.md' ($provenance.Replace($next, $entry.Replace("`r`n", "`n") + "`n" + $next))
Write-Lf "submission/overlay/packages/kernel/patches/$name" ([IO.File]::ReadAllText((Join-Path $root 'experimental/charge-rate-policy/charge-rate-policy.patch')))
$diffs = @()
Push-Location $root
try {
    foreach ($path in $paths) {
        $before = if (Test-Path "upstream/$path") { "upstream/$path" } else { '/dev/null' }
        $lines = & git -c core.safecrlf=false diff --no-index -- $before "submission/overlay/$path"
        if ($LASTEXITCODE -ne 1) { throw "Expected a nonempty diff for $path, exit $LASTEXITCODE" }
        $diff = ($lines -join "`n") + "`n"
        $diff = $diff.Replace('a/upstream/', 'a/').Replace('b/upstream/', 'b/')
        $diff = $diff.Replace('a/submission/overlay/', 'a/').Replace('b/submission/overlay/', 'b/')
        $diffs += $diff
    }
    Write-Lf 'submission/armada-kpfe-charge-limit.patch' ($diffs -join '')
    Write-Lf 'experimental/charge-rate-policy/armada-charge-rate-policy.patch' ($diffs -join '')
} finally { Pop-Location }
Write-Output 'Prepared three-file Armada diff. Run tests/verify_artifacts.py next.'
