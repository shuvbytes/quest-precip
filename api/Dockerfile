# Point forecast API for Hugging Face Spaces (Docker SDK). Small image: no GRIB libraries; the data is read from the
# live GitHub Pages site at start-up (see app.py).
FROM python:3.11-slim

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user app.py pointcore.py ./

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
