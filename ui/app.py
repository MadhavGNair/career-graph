"""CareerGraph Streamlit entry point (home page). Pages live in ui/pages/."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from common import get_service, page_setup

settings = page_setup("CareerGraph")
svc = get_service()
pending = svc.list_pending()
apps = svc.list_applications()
c1, c2, c3 = st.columns(3)
c1.metric("Mode", settings.app_mode)
c2.metric("Threads waiting for you", len(pending))
c3.metric("Applications ready", sum(a.status == "ready" for a in apps))
st.markdown(
    "1. **Run** a search (or let cron do it).\n"
    "2. **Shortlist**: approve, reject or defer jobs; reason tags teach the matcher.\n"
    "3. **Documents**: review drafts (claims cite your evidence); edit, regenerate, approve.\n"
    "4. **Tracker** and **Insights**. CareerGraph never applies or sends anything for you."
)
for label, page in [
    ("Run", "pages/1_Run.py"),
    ("Shortlist", "pages/2_Shortlist.py"),
    ("Documents", "pages/3_Documents.py"),
    ("Tracker", "pages/4_Tracker.py"),
    ("Insights", "pages/5_Insights.py"),
]:
    st.page_link(page, label=label)
