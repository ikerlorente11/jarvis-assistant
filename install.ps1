# Instalación reproducible de JARVIS Assistant (docs/07).
# Uso: .\install.ps1   (en otra máquina: git clone + este script)
# Fase 0: piezas base + venv. El autoarranque llega en fase 6.

$ErrorActionPreference = "Stop"

function Ensure-Winget($id, $name) {
    winget list --id $id -e --accept-source-agreements | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[ok] $name ya instalado"
    } else {
        Write-Host "[..] Instalando $name..."
        winget install --id $id -e --silent --accept-source-agreements --accept-package-agreements
    }
}

# 1. Piezas nativas
Ensure-Winget "Python.Python.3.13" "Python 3.13"
Ensure-Winget "Ollama.Ollama" "Ollama"
Ensure-Winget "voidtools.Everything" "Everything"
Ensure-Winget "voidtools.Everything.Cli" "es.exe (Everything CLI)"

# 2. Venv + dependencias fijadas
if (-not (Test-Path ".venv")) {
    Write-Host "[..] Creando venv..."
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Modelos según el perfil detectado
$profileOut = & .\.venv\Scripts\python.exe -m jarvis.profile
Write-Host $profileOut
if ($profileOut -match "LLM:\s+(qwen\S+)") {
    $model = $Matches[1]
    Write-Host "[..] Descargando modelo LLM $model (puede tardar)..."
    ollama pull $model
} else {
    Write-Host "[ok] Perfil sin LLM: no se descarga modelo"
}

Write-Host "`n[ok] Instalación completada. Prueba: .\.venv\Scripts\python.exe -m jarvis.profile"
