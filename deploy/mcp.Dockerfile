# MCP server (build123d/OpenCascade) over streamable HTTP. Build context: repo root.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
# OpenCascade's wheels link against libGL and glib even without a display.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
# arduino-cli + the AVR, Teensy and ESP32 cores (about 2 GB) and common libraries: every generated sketch is
# compiled before the guide is shown (bench/sketch.py), one compile at a time. Keep the library list in step with the ones the planner may use.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://downloads.arduino.cc/arduino-cli/arduino-cli_1.2.2_Linux_64bit.tar.gz | tar -xz -C /usr/local/bin arduino-cli \
    && arduino-cli config init \
    && arduino-cli config add board_manager.additional_urls https://www.pjrc.com/teensy/package_teensy_index.json \
       https://espressif.github.io/arduino-esp32/package_esp32_index.json \
    && arduino-cli core update-index \
    && arduino-cli core install arduino:avr@1.8.8 teensy:avr@1.62.0 esp32:esp32@3.3.12 \
    && arduino-cli lib install LedControl Servo ESP32Servo "LiquidCrystal I2C" "DHT sensor library" "Adafruit Unified Sensor" \
       "Adafruit NeoPixel" NewPing Keypad \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app/mcp-server
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY mcp-server/pyproject.toml mcp-server/uv.lock mcp-server/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY mcp-server/ ./
COPY parts/ /app/parts/
RUN uv sync --frozen --no-dev
ENV MCP_TRANSPORT=http MCP_PORT=8000 PHYSICAL_STUDIO_OUT=/data/out
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "physical-studio-mcp"]
