# Base image with Python installed
FROM python:3.12-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (better Docker caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your bot code
COPY . .

# Command to start your bot
CMD ["python", "main.py"]
