# MEDAIGENCY

WhatsApp-based emergency fire-reporting and dispatch system, built for the AI4PURPOSE Hackathon (2026).

Reports come in over WhatsApp (Twilio sandbox), get filtered/classified by severity and keyword analysis, and are routed to the nearest available hospital, with an n8n-orchestrated backend (Docker/ngrok) and file-based session persistence.

## Structure

- `src/` — backend and processing logic
  - `app.py` — main backend service
  - `IncidentFilter.java` — filters incoming incident reports
  - `SeverityCalculator.java` — computes incident severity (`Role` enum: VICTIM/OBSERVER)
  - `KeywordAI.java` — keyword-based incident/text analysis (`KeywordAI` class)
- `public/` — front-end
  - `index.html` — landing page
  - `dashboard.html` — dispatch dashboard
- `data/`
  - `hospitals_directory.md` — Lebanon hospital directory with contact info
  - `sample_incident_reports.txt` — sample/test incident reports
- `demo/` — final demo video
