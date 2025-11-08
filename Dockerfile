FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLECORS=true
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true
EXPOSE 8080
CMD ["streamlit", "run", "dashboard/app.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
