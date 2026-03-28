param(
  [switch]$Persist
)

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$global:OutputEncoding = $utf8
chcp 65001 > $null

Write-Host "UTF-8 enabled for current PowerShell session."

if ($Persist) {
  if (-not (Test-Path -Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
  }

  $marker = "# with-langgraph-fastapi UTF-8 profile block"
  $block = @"
$marker
`$utf8 = New-Object System.Text.UTF8Encoding(`$false)
[Console]::InputEncoding = `$utf8
[Console]::OutputEncoding = `$utf8
`$global:OutputEncoding = `$utf8
chcp 65001 > `$null
"@
  $existing = Get-Content -Raw -Path $PROFILE
  if ($existing -notmatch [regex]::Escape($marker)) {
    Add-Content -Path $PROFILE -Value "`r`n$block`r`n"
    Write-Host "UTF-8 profile block added to $PROFILE."
  } else {
    Write-Host "UTF-8 profile block already exists in $PROFILE."
  }
}
