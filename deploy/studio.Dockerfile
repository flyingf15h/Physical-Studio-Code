# Circuit Studio: Senna's Streamlit app (photos + wiring notes -> Gemini -> breadboard GLB),
# served under https://$DOMAIN/studio/. Build context: repo root.
FROM python:3.12-slim
WORKDIR /app
COPY circuit-studio/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY circuit-studio/ ./
EXPOSE 8501
USER nobody
ENV HOME=/tmp
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.baseUrlPath=studio", "--server.headless=true", "--browser.gatherUsageStats=false"]
