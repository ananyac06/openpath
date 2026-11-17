"""Synthetic fixtures for offline ATS connector tests.

NOTE: All records in this file are synthetic and for testing purposes only.
"""

SYNTHETIC_GREENHOUSE_PAYLOAD = """{
  "jobs": [
    {
      "id": 101,
      "internal_job_id": 201,
      "title": "Software Engineering Intern",
      "updated_at": "2026-11-01T12:00:00Z",
      "requisition_id": "REQ-101",
      "location": {
        "name": "Bangalore, India"
      },
      "absolute_url": "https://boards.greenhouse.io/synthetic_corp/jobs/101",
      "departments": [
        {"id": 1, "name": "Engineering"}
      ],
      "offices": [
        {"id": 1, "name": "Bangalore Office"}
      ],
      "content": "<p>We are seeking a <strong>Software Engineering Intern</strong> to join our team in Bangalore, India. Requirements: Python, SQL, REST APIs.</p>"
    },
    {
      "id": 102,
      "internal_job_id": 202,
      "title": "US Site Reliability Engineer",
      "updated_at": "2026-11-01T12:00:00Z",
      "requisition_id": "REQ-102",
      "location": {
        "name": "New York, USA"
      },
      "absolute_url": "https://boards.greenhouse.io/synthetic_corp/jobs/102",
      "departments": [
        {"id": 1, "name": "Infrastructure"}
      ],
      "offices": [
        {"id": 2, "name": "NYC Office"}
      ],
      "content": "<p>Must be located in the US. US work authorization required.</p>"
    }
  ],
  "meta": {
    "total": 2
  }
}"""

SYNTHETIC_LEVER_PAYLOAD = """[
  {
    "id": "lever-item-1",
    "text": "Backend Engineering Trainee",
    "hostedUrl": "https://jobs.lever.co/synthetic_lever/lever-item-1",
    "applyUrl": "https://jobs.lever.co/synthetic_lever/lever-item-1/apply",
    "categories": {
      "commitment": "Full-time",
      "department": "Engineering",
      "location": "Bengaluru, India",
      "team": "Core Platform"
    },
    "descriptionPlain": "Join as a Backend Engineering Trainee in Bengaluru. Skills: Python, FastAPI, PostgreSQL.",
    "description": "<p>Join as a <strong>Backend Engineering Trainee</strong> in Bengaluru. Skills: Python, FastAPI, PostgreSQL.</p>"
  }
]"""

SYNTHETIC_ASHBY_PAYLOAD = """{
  "apiVersion": "1",
  "jobs": [
    {
      "title": "AI Research Fellow",
      "location": "Remote",
      "isRemote": true,
      "workplaceType": "Remote",
      "jobUrl": "https://jobs.ashbyhq.com/synthetic_ashby/ai-research-fellow",
      "applyUrl": "https://jobs.ashbyhq.com/synthetic_ashby/ai-research-fellow/apply",
      "descriptionHtml": "<p>Open worldwide to researchers across India and globally. Working on open-source deep learning.</p>",
      "descriptionPlain": "Open worldwide to researchers across India and globally. Working on open-source deep learning."
    }
  ],
  "compensation": {
    "compensationTierSummary": "$25,000 - $35,000 / year"
  }
}"""
