# Builds "dist\LEGO Order Scraper\LEGO Order Scraper.exe" and a zip of it, on a Windows PC,
# for that PC's CPU (x64 or arm64 -- whichever Python you install).
# (GitHub Actions does the same thing automatically: .github/workflows/windows-app.yml)
# Needs Python 3.10+ from python.org. Usage, in PowerShell:
#   cd windows-app
#   powershell -ExecutionPolicy Bypass -File build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Creating build environment"
python -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv-build\Scripts\python.exe -m pip install --quiet -r requirements-windows.txt

Write-Host "==> Making the icon"
& .\.venv-build\Scripts\python.exe -c "from PIL import Image; Image.open('icon.png').save('icon.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

Write-Host "==> Building (takes a few minutes)"
if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean LEGO_Order_Scraper_win.spec

$arch = (& .\.venv-build\Scripts\python.exe -c "import platform; print({'AMD64': 'x64', 'ARM64': 'arm64'}.get(platform.machine(), platform.machine()))").Trim()
$exe = "dist\LEGO Order Scraper\LEGO Order Scraper.exe"
Write-Host "==> Checking it's built for $arch and runs"
& .\.venv-build\Scripts\python.exe check_exe_arch.py $arch "dist\LEGO Order Scraper"
if ($LASTEXITCODE -ne 0) { throw "built for the wrong CPU" }
& $exe --run-scraper --version
& $exe --self-test
if ($LASTEXITCODE -ne 0) { throw "self-test failed" }

Write-Host "==> Zipping"
Compress-Archive -Force -Path "dist\LEGO Order Scraper" -DestinationPath "dist\LEGO-Order-Scraper-windows-$arch.zip"
Write-Host ""
Write-Host "Done: $PWD\dist\LEGO-Order-Scraper-windows-$arch.zip"
