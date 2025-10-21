Write-Host "========================================================"
Write-Host "  PATCH HOTEL-RM-APP : Excel/PDF exports + main_reload"
Write-Host "========================================================"

# Vérifier qu'on est bien dans un dépôt Git
if (-not (Test-Path ".git")) {
    Write-Host "❌ Ce dossier n'est pas un dépôt Git."
    exit
}

# Mise à jour de la branche main
Write-Host "🌀 Mise à jour de la branche main..."
git checkout main
git pull origin main

# Création de la nouvelle branche
Write-Host "🌿 Création de la branche main_reload..."
git checkout -b main_reload

# Chemin du patch
$zipPath = "$env:USERPROFILE\Downloads\hotel-rm-app-stable-patch.zip"
if (-not (Test-Path $zipPath)) {
    Write-Host "⚠️  Fichier non trouvé : $zipPath"
    Write-Host "Télécharge hotel-rm-app-stable-patch.zip avant d'exécuter ce script."
    exit
}

# Extraction du patch
Write-Host "📦 Extraction du patch..."
Expand-Archive -Force $zipPath -DestinationPath "./patch_temp"

# Copie des fichiers
if (-not (Test-Path "app")) { New-Item -ItemType Directory -Force -Path "app" | Out-Null }
if (-not (Test-Path "frontend")) { New-Item -ItemType Directory -Force -Path "frontend" | Out-Null }

Copy-Item "patch_temp/export_utils.py" -Destination "app" -Force
Copy-Item "patch_temp/export_endpoints.py" -Destination "app" -Force
Copy-Item "patch_temp/frontend/export.js" -Destination "frontend" -Force

# Ajout des dépendances
Write-Host "🧩 Ajout des dépendances Python..."
Add-Content requirements.txt "pandas==2.2.2"
Add-Content requirements.txt "openpyxl==3.1.5"
Add-Content requirements.txt "reportlab==4.2.2"

# Message d'insertion dans main.py
Write-Host "--------------------------------------------------------"
Write-Host "⚙️  Vérifie que tu as ajouté dans main.py :"
Write-Host "   from export_endpoints import router as export_router"
Write-Host "   app.include_router(export_router)"
Write-Host "--------------------------------------------------------"
Pause

# Commit et push
git add app/export_utils.py app/export_endpoints.py frontend/export.js requirements.txt
git commit -m "🚀 Added Excel/PDF export endpoints + frontend helper (main_reload)"
git push origin main_reload

Write-Host "✅ Patch appliqué et poussé avec succès !"
Write-Host "Branche : main_reload"
Write-Host "========================================================"
Pause
