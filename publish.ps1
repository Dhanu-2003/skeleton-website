<#
.SYNOPSIS
  Publishes the website on GitHub Pages, in a NEW public repository of its own (the app's code repository is not touched and stays private),
  with the installer as a GitHub Release. Run it once; run it again to publish a new installer version.

.DESCRIPTION
  1. GitHub CLI: installed with winget if missing; you sign in once in the browser (gh auth login).
  2. The repository <your account>/<Repo> is made (public) if it does not exist, and GitHub Pages is switched on (built by GitHub Actions).
  3. The website's source (no database, no secret key, no local settings) is pushed; .github/workflows/pages.yml then tests it, builds the static
     site and publishes it.
  4. The installer named in the app's latest.json is published as the Release v<version>; the site's Download button points at it and the site shows
     GitHub's own download count.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File publish.ps1
  powershell -ExecutionPolicy Bypass -File publish.ps1 -Repo nova-website
#>
param(
    [string]$Repo = "nova-website",
    [string]$ReleasesDir = (Join-Path $PSScriptRoot "..\nova-windows\packaging\build\out")
)
$ErrorActionPreference = "Continue"      # (each step's exit code is checked; Windows PowerShell would otherwise stop on a program's ordinary stderr)
function Say($t) { Write-Host "==> $t" -ForegroundColor Cyan }

# ---- 1. GitHub CLI, signed in
$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) {
    Say "Installing GitHub CLI (winget)"
    winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
    $gh = "C:\Program Files\GitHub CLI\gh.exe"
    if (-not (Test-Path $gh)) { throw "GitHub CLI did not install. Install it from https://cli.github.com and run this again." }
}
& $gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say "Sign in to GitHub (a browser opens; allow the 'repo' and 'workflow' access)"
    & $gh auth login --web --git-protocol https --scopes "repo,workflow"
    if ($LASTEXITCODE -ne 0) { throw "GitHub sign-in did not finish." }
}
$owner = (& $gh api user --jq .login).Trim()
$full = "$owner/$Repo"
$pagesUrl = "https://$($owner.ToLower()).github.io/$Repo/"
Say "Publishing to $full  ->  $pagesUrl"

# ---- the release to publish
$latest = Get-Content (Join-Path $ReleasesDir "latest.json") -Raw | ConvertFrom-Json
$exe = Join-Path $ReleasesDir $latest.url
if (-not (Test-Path $exe)) { throw "The installer $exe is not there: build it first." }
$ver = $latest.version
$tag = "v$ver"

# ---- 2. the repository and GitHub Pages
& $gh repo view $full 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say "Making the public repository $full"
    & $gh repo create $full --public --description "The website of the app: download it, see how it works." | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "The repository could not be made." }
}
& $gh api "repos/$full/pages" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say "Switching on GitHub Pages (built by GitHub Actions)"
    & $gh api -X POST "repos/$full/pages" -f build_type=workflow | Out-Null
}

# ---- 3. the website's source, without anything local or secret
$stage = Join-Path $env:TEMP "site-publish\$Repo"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
robocopy $PSScriptRoot $stage /E /XD data dist __pycache__ .git /XF config.json release.json *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
[ordered]@{ version = $ver; file = $latest.url; size = $latest.size; sha256 = $latest.sha256; notes = $latest.notes; built = $latest.built
            download_url = "https://github.com/$full/releases/download/$tag/$($latest.url)" } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $stage "release.json")
Push-Location $stage
try {
    git init -q -b main
    git add -A
    git add -f release.json      # (ignored in the app's own repository; the published site needs it)
    git -c core.autocrlf=false commit -q -m "Publish the website ($tag)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    git remote add origin "https://github.com/$full.git"
    & $gh auth setup-git | Out-Null
    git push -q -f origin main
    if ($LASTEXITCODE -ne 0) { throw "The push did not work." }
} finally { Pop-Location }

# ---- 4. the installer as the GitHub Release
& $gh release view $tag --repo $full 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Say "Publishing the installer as release $tag"
    & $gh release create $tag $exe --repo $full --title "$tag" --notes "$($latest.notes)`n`nSHA-256: $($latest.sha256)"
} else {
    Say "Release $tag exists: replacing its installer"
    & $gh release upload $tag $exe --repo $full --clobber
}
& $gh workflow run pages.yml --repo $full 2>$null | Out-Null

Say "Done. The site is being built by GitHub Actions (about a minute):"
Write-Host "    $pagesUrl" -ForegroundColor Green
Write-Host "    Progress: https://github.com/$full/actions"
