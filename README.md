# Voice Outbound

A Twilio-based voice outbound calling application built with Flask.

## Features

- Outbound voice calling using Twilio
- Flask web application
- Environment-based configuration

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your Twilio credentials
4. Run the application:
   ```bash
   python app.py
   ```

## Environment Variables

See `.env.example` for required environment variables.

## Deployment

This application is configured for deployment on Render. See `render.yaml` for configuration.
