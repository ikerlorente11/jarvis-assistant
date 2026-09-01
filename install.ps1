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

# 3. Voces TTS — corren en CPU en todos los perfiles
New-Item -ItemType Directory -Force "models\piper" | Out-Null
foreach ($voz in @("es_ES-davefx-medium", "es_ES-sharvard-medium", "es_ES-carlfm-x_low")) {
    if (-not (Test-Path "models\piper\$voz.onnx")) {
        Write-Host "[..] Descargando voz de Piper $voz..."
        & .\.venv\Scripts\python.exe -m piper.download_voices $voz --data-dir "models\piper"
    }
}
# Kokoro (mas calidad; voces es: dora/alex/santa)
New-Item -ItemType Directory -Force "models\kokoro" | Out-Null
if (-not (Test-Path "models\kokoro\kokoro-v1.0.onnx")) {
    Write-Host "[..] Descargando modelo Kokoro (~310 MB)..."
    Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx" -OutFile "models\kokoro\kokoro-v1.0.onnx"
    Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin" -OutFile "models\kokoro\voices-v1.0.bin"
}

# 4. Modelos según el perfil detectado
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
