$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$rows = Get-ChildItem -LiteralPath $root -Recurse -Force -File | Where-Object {
    $_.Name -ne 'MANIFEST.sha256' -and $_.FullName -notmatch '[\\/](\.git|__pycache__)[\\/]'
} | ForEach-Object {
    $relative = [IO.Path]::GetRelativePath($root, $_.FullName).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $relative"
} | Sort-Object { ($_ -split '  ', 2)[1] }
[IO.File]::WriteAllText((Join-Path $root 'MANIFEST.sha256'), ($rows -join "`n") + "`n", [Text.UTF8Encoding]::new($false))
