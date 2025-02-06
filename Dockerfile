# Use a Python 3.9 image compatible with Render
FROM python:3.9-slim

# Update OS packages and install CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install pip dependencies
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your files
COPY . /app

# Expose the port and specify the default run command
EXPOSE 5055
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5055"]
