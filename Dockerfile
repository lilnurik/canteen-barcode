# Use the official Python slim image as the base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt and install dependencies
COPY requirements.txt requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port that Render will use. This can be adjusted if needed.
EXPOSE 5055

# Start the application with gunicorn, using the PORT environment variable (defaulting to 5055 if not set)
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-5055}"]
