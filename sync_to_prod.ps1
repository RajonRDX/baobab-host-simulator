<#
  sync_to_prod.ps1
  Copies changes from the TEST folder to the PROD (GitHub) folder
  while leaving prod-specific files (URLs / env config) untouched.

  Usage (PowerShell):
    .\sync_to_prod.ps1              # DRY RUN - only shows what would change
    .\sync_to_prod.ps1 -Apply       # actually copies the files
    .\sync_to_prod.ps1 -Apply -Mirror   # also DELETES files in prod that no longer exist in test (careful)
#>
param(
    [switch]$Apply,
    [switch]$Mirror
)

$src = "E:\HOST_VSCODE\host-simulator"
$dst = "E:\HOST_VSCODE\host-simulator-github-prod"

# ---- Folders never copied (build output, dependencies, git data) ----
$excludeDirs = @(
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".pytest_cache", ".vscode", "logs"
)

# ---- Files NEVER overwritten in prod (these hold your prod URLs / secrets) ----
# EDIT THIS LIST to match where your URLs really live.
$excludeFiles = @(
    "config.py",            # backend\app\config.py  (HSM_MODE, HSM_REMOTE_URL, CORS, etc.)
    ".env", ".env.local", ".env.production", ".env.development",
    "*.db", "*.sqlite", "*.log", "*.pyc"
)

if (-not (Test-Path $src)) { Write-Error "Test folder not found: $src"; exit 1 }
if (-not (Test-Path $dst)) { Write-Error "Prod folder not found: $dst"; exit 1 }

$args = @($src, $dst)
if ($Mirror) { $args += "/MIR" } else { $args += "/E" }
$args += "/XD"; $args += $excludeDirs
$args += "/XF"; $args += $excludeFiles
$args += @("/NJH", "/NJS", "/NP", "/NDL")
if (-not $Apply) { $args += "/L" }   # /L = list only (dry run)

if ($Apply) {
    Write-Host "=== APPLYING changes: TEST -> PROD ===" -ForegroundColor Yellow
} else {
    Write-Host "=== DRY RUN (nothing is copied). Use -Apply to copy. ===" -ForegroundColor Cyan
}

robocopy @args
if ($LASTEXITCODE -ge 8) { Write-Error "Robocopy failed (exit code $LASTEXITCODE)"; exit $LASTEXITCODE }

# ---- Safety scan: look for local URLs that leaked into prod files ----
Write-Host "`n=== Scanning prod for local URLs (127.0.0.1 / localhost) ===" -ForegroundColor Cyan
$hits = Get-ChildItem $dst -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $p = $_.FullName
        -not ($excludeDirs | Where-Object { $p -like "*\$_\*" }) -and
        $_.Extension -in ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".env", ".md", ".yml", ".yaml"
    } |
    Select-String -Pattern "127\.0\.0\.1|localhost" -ErrorAction SilentlyContinue

if ($hits) {
    $hits | ForEach-Object { "{0}:{1}  {2}" -f $_.Path, $_.LineNumber, $_.Line.Trim() }
    Write-Host "`nReview the lines above - make sure none of them should be a prod URL." -ForegroundColor Yellow
} else {
    Write-Host "No local URLs found." -ForegroundColor Green
}

if ($Apply) {
    Write-Host "`n=== git status in prod ===" -ForegroundColor Cyan
    git -C $dst status --short
    Write-Host "`nNext: review with 'git diff', then commit and push." -ForegroundColor Green
}
