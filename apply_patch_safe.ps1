$ErrorActionPreference = "Stop"

function Write-Color([string]$Text,[ConsoleColor]$Color="White") {
  $old = $Host.UI.RawUI.ForegroundColor
  $Host.UI.RawUI.ForegroundColor = $Color
  Write-Host $Text
  $Host.UI.RawUI.ForegroundColor = $old
}

Write-Color "========================================================" Cyan
Write-Color "  PATCH HOTEL-RM-APP : Excel/PDF exports + main_reload" Cyan
Write-Color "========================================================" Cyan

# Vérification de Git
if (-not (Test-Path ".git")) { Write-Color "❌ Ce dossier n'est pas un dépôt Git." Red; exit 1 }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Write-Color "❌ Git n'est pas installé dans le PATH." Red; exit 1 }

# Sauvegarde du main.py
if (Test-Path ".\main.py") {
  Copy-Item ".\main.py" ".\main_backup_before_patch.py" -Force
  Write-Color "🧷 Sauvegarde : main_backup_before_patch.py créée." Yellow
} else {
  Write-Color "⚠️  main.py introuvable à la racine. Je continue mais l'injection sera ignorée." Yellow
}

# Extraction du patch
$zip = ".\hotel-rm-app-stable-patch.zip"
$dest = ".\patch_temp_auto"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
if (-not (Test-Path $zip)) { Write-Color "❌ ZIP introuvable : $zip" Red; exit 1 }
Write-Color "📦 Extraction du patch..." Yellow
Expand-Archive -Force $zip -DestinationPath $dest

# Copie des fichiers
New-Item -ItemType Directory -Force -Path ".\app" | Out-Null
New-Item -ItemType Directory -Force -Path ".\frontend" | Out-Null
Copy-Item "$dest\app\export_utils.py" ".\app\" -Force
Copy-Item "$dest\app\export_endpoints.py" ".\app\" -Force
Copy-Item "$dest\frontend\export.js" ".\frontend\" -Force
Copy-Item "$dest\frontend\export_buttons_example.html" ".\frontend\" -Force
Write-Color "📁 Fichiers copiés dans app/ et frontend/." Green

# Injection automatique dans main.py
if (Test-Path ".\main.py") {
  $content = Get-Content ".\main.py" -Raw
  $needImport = ($content -notmatch "from\s+export_endpoints\s+import\s+router\s+as\s+export_router")
  $needInclude = ($content -notmatch "app\.include_router\s*\(\s*export_router\s*\)")

  if ($needImport -or $needInclude) {
    if ($needImport) {
      $content = "from export_endpoints import router as export_router`n" + $content
    }
    if ($needInclude) {
      $content = $content + "`n# Auto-injected export router`napp.include_router(export_router)`n"
    }
    Set-Content ".\main.py" $content -NoNewline
    Write-Color "🪄 Injection auto dans main.py effectuée." Green
  } else {
    Write-Color "✅ main.py contient déjà l'import et l'include." Green
  }
}  # 👈 <<< CETTE LIGNE DOIT ÊTRE PRÉSENTE

# Workflow Git
Write-Color "🌀 Mise à jour de main..." Yellow
git checkout main | Out-Null
git pull origin main | Out-Null

Write-Color "🌿 Création/mise à jour de main_reload..." Yellow
git checkout -B main_reload | Out-Null

git add app/export_utils.py app/export_endpoints.py frontend/export.js frontend/export_buttons_example.html requirements.txt main.py
$didCommit = $true
try { git commit -m "✅ Patch stable : ajout export Excel/PDF" | Out-Null } catch { $didCommit = $false; Write-Color "ℹ️  Aucun changement à committer (peut-être déjà appliqué)." Yellow }
git push origin main_reload --force | Out-Null
$commitId = (git rev-parse --short HEAD).Trim()

# Vérification de l'API
$api = "https://api-folkestone.e-hotelmanager.com/health"
Write-Color "🌐 Vérification API : $api" Yellow
$apiStatus = "N/A"
try {
  $resp = Invoke-WebRequest -Uri $api -Method GET -TimeoutSec 15
  $apiStatus = "$($resp.StatusCode)"
  if ($resp.StatusCode -eq 200) { Write-Color "✅ API Folkestone opérationnelle (200)" Green } else { Write-Color "⚠️ API a répondu avec le statut $($resp.StatusCode)" Yellow }
} catch { Write-Color "⚠️ Impossible de joindre l'API: $($_.Exception.Message)" Yellow }

# Résumé final
Write-Color "----------------------------------------" Cyan
Write-Color "✅ PATCH APPLIQUÉ" Green
Write-Color "📦 Fichiers mis à jour :" White
Write-Color "  ✔ app/export_utils.py" White
Write-Color "  ✔ app/export_endpoints.py" White
Write-Color "  ✔ frontend/export.js" White
Write-Color "  ✔ frontend/export_buttons_example.html" White
Write-Color "----------------------------------------" Cyan
Write-Color "🧩 Branche : main_reload" White
Write-Color "🔖 Commit ID : $commitId" White
Write-Color "🌐 API health : $apiStatus" White
Write-Color "----------------------------------------" Cyan
