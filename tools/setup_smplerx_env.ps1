# SMPLer-X research environment setup (PowerShell)
# Run from D:\blender5.2\pose_plugin
# Uses uv pip against the venv interpreter explicitly; uv venvs do not ship pip.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvDir = Join-Path $Root "_envs\smplerx"
$Py = Join-Path $EnvDir "Scripts\python.exe"
$Repo = Join-Path $Root "_research\repos\SMPLer-X"

Write-Host "== uv python 3.8 =="
uv python install 3.8

Write-Host "== create venv (clean) =="
uv venv --python 3.8 --clear $EnvDir

Write-Host "== link model directories into the SMPLer-X checkout =="
$ModelRoot = Join-Path $Root "_models\smplerx"
$HumanLink = Join-Path $Repo "common\utils\human_model_files"
$WeightLink = Join-Path $Repo "pretrained_models"
if (-not (Test-Path -LiteralPath $HumanLink)) {
    cmd /c mklink /J "$HumanLink" "$(Join-Path $ModelRoot 'common\utils\human_model_files')" | Out-Null
}
if (-not (Test-Path -LiteralPath $WeightLink)) {
    cmd /c mklink /J "$WeightLink" "$(Join-Path $ModelRoot 'pretrained_models')" | Out-Null
}

Write-Host "== torch 1.12 cu113 =="
uv pip install --python $Py --index-strategy unsafe-best-match torch==1.12.0+cu113 torchvision==0.13.0+cu113 torchaudio==0.12.0 --index-url https://download.pytorch.org/whl/cu113 --extra-index-url https://pypi.org/simple

Write-Host "== numeric pins + pip (for chumpy build) =="
uv pip install --python $Py "numpy==1.23.5" "scipy==1.10.1" "setuptools==69.5.1" "pip==24.0" "wheel"
uv pip install --python $Py --no-build-isolation "chumpy==0.70"

Write-Host "== mmcv-full 1.7.1 =="
uv pip install --python $Py mmcv-full==1.7.1 -f https://download.openmmlab.com/mmcv/dist/cu113/torch1.12.0/index.html

Write-Host "== SMPLer-X requirements =="
Push-Location $Repo
uv pip install --python $Py --no-build-isolation -r requirements.txt
uv pip install --python $Py "yapf==0.40.1"
Write-Host "== mmpose =="
Push-Location "main\transformer_utils"
uv pip install --python $Py -v -e .
Pop-Location
Pop-Location

Write-Host "== runtime compatibility patches =="
& $Py (Join-Path $Root "tools\patch_smplerx_runtime.py")

Write-Host "Done. Set Pose2Rig > Worker Python to: $Py"
