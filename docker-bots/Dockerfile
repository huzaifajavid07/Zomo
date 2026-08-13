# ══════════════════════════════════════════════════════════════
# Zomo Multi-Bot — Dockerfile
# Headless Playwright Chromium container for Zoom Web Client
# ══════════════════════════════════════════════════════════════

FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (Chromium only for lighter image)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy bot scripts
COPY zoom_web_bot.py .
COPY generate_mock_video.py .

# Generate the mock video file at build time
RUN python generate_mock_video.py --output /app/mock_face.y4m --width 640 --height 480 --fps 15 --duration 20

# Environment defaults (overridable via docker-compose or docker run)
ENV MEETING_URL=""
ENV BOT_NAME="Participant"
ENV CHAT_INTERVAL_MIN="15"
ENV CHAT_INTERVAL_MAX="45"
ENV CHAT_MESSAGES='["Hi everyone!","Can you hear me?","Great presentation!","Interesting point.","Thanks for sharing.","I agree with that.","Sorry I am late.","Good morning!","Sounds good to me.","Thanks for the update."]'
ENV HEADLESS="true"
ENV MOCK_VIDEO="/app/mock_face.y4m"
ENV BOT_TIMEOUT="3600"

# Health check: verify python is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "print('healthy')" || exit 1

# Entry point
ENTRYPOINT ["python", "zoom_web_bot.py"]
