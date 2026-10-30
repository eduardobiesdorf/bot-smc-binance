@echo off
REM Cria a tarefa que roda o radar a cada 15 minutos, no minuto exato.
REM Execute este arquivo UMA VEZ, como administrador.

schtasks /Create /TN "RadarSMC" /TR "\"%~dp0rodar_radar.bat\"" /SC MINUTE /MO 15 /F
echo.
echo Tarefa criada. Para conferir:   schtasks /Query /TN RadarSMC
echo Para remover depois:            schtasks /Delete /TN RadarSMC /F
pause
