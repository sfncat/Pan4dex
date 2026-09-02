@echo off
taskkill /F /IM pan4dex* /T 2>nul
timeout /t 2 /nobreak >nul
cd /d D:\workspace\2026\pan4dex\dist
del /F /Q *.exe 2>nul
del /Q pan4dex.zip.old 2>nul
powershell -Command "Expand-Archive -Path pan4dex.zip -DestinationPath . -Force"
dir *.exe
