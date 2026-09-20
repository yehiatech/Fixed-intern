FROM python:3.11-alpine

WORKDIR /app

# Ensure python logs show up immediately in Docker logs (and Grafana)
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts
COPY . .

# Setup Alpine Cron
# Trigger runs every 15 minutes. Sync runs every 1 minute.
# We redirect output to /proc/1/fd/1 so that Grafana Alloy can see the logs!
RUN echo "*/15 * * * * python /app/call_trigger.py > /proc/1/fd/1 2>&1" > /var/spool/cron/crontabs/root && \
    echo "* * * * * python /app/call_result_sync.py > /proc/1/fd/1 2>&1" >> /var/spool/cron/crontabs/root

# Run cron daemon in the foreground
CMD ["crond", "-f", "-l", "2"]
