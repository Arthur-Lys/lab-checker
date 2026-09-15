# Lab checker UI

A front-end for the university lab auto-checker (`laboratory-checker-actions.onrender.com`) that keeps the form
filled in, submits several labs in one go and explains every verdict in plain words.

It does not grade anything itself: every request goes to the teacher's server, only the answer is decoded.

- `index.html` — the page (React from a CDN, no build step)
- `api/submit.py` — Vercel Python function that forwards one submission and strips the HTML from the reply

Run locally: `vercel dev`
