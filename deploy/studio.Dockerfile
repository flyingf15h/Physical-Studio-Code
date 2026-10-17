# Circuit Studio: Senna's Streamlit app (photos + wiring notes -> Gemini -> breadboard GLB),
# served under https://$DOMAIN/studio/. Build context: repo root.
# The Build helper also reads the measured parts library (sizes, Uno pin positions) and the
# traffic-light sketch, so those are copied next to it.
FROM python:3.12-slim
WORKDIR /app
COPY circuit-studio/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY circuit-studio/ ./
COPY parts/ ./parts/
COPY firmware/traffic-light/ ./firmware/traffic-light/
EXPOSE 8501
USER nobody
ENV HOME=/tmp
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.baseUrlPath=studio", "--server.headless=true", "--browser.gatherUsageStats=false"]
