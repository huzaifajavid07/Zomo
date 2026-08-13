@echo off
:: ══════════════════════════════════════════════
:: Zomo Human Bots — Quick Launcher (Windows)
:: ══════════════════════════════════════════════

SET MEETING_URL=%1
SET BOT_COUNT=%2

IF "%MEETING_URL%"=="" (
    SET /P MEETING_URL="Enter Zoom meeting URL: "
)

IF "%BOT_COUNT%"=="" (
    SET /P BOT_COUNT="Number of bots (default 5): "
    IF "%BOT_COUNT%"=="" SET BOT_COUNT=5
)

echo.
echo   Zomo Human Bots
echo   ═══════════════════════════════════════
echo   Meeting : %MEETING_URL%
echo   Bots    : %BOT_COUNT%
echo   Mode    : Headless Chromium (Multi-Context)
echo   Names   : names.json
echo   Messages: messages.json
echo   ═══════════════════════════════════════
echo.

python zoom_human_bots.py ^
  --meeting-url "%MEETING_URL%" ^
  --count %BOT_COUNT% ^
  --chat-min 20 ^
  --chat-max 60 ^
  --join-delay-min 8 ^
  --join-delay-max 25 ^
  --headless ^
  --mock-video ./mock_face.y4m ^
  --names-file ./names.json ^
  --messages-file ./messages.json

pause
