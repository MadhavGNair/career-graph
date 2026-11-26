"""Insights: skills demand over time, token usage (and USD when priced) per run."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from common import get_service, page_setup

settings = page_setup("Insights")
svc = get_service()

st.subheader("Skills demand over time")
trend = svc.skills_trend()
if trend:
    df = pd.DataFrame(trend).pivot_table(
        index="week", columns="skill", values="count", fill_value=0
    )
    st.line_chart(df)
    st.caption("Postings per week requiring each of the most demanded skills (must + nice).")
else:
    st.info("No analysed postings yet.")

st.subheader("LLM usage per run")
usage = svc.usage_by_run()
if usage:
    df = pd.DataFrame(usage)
    df["tokens"] = df["input_tokens"] + df["output_tokens"]
    st.bar_chart(df.set_index("run_id")["tokens"])
    st.dataframe(df, hide_index=True)
    if bool(df["fake"].any()):
        st.caption(
            "Rows marked fake come from the demo's fake LLM: token counts are estimates "
            "(characters / 4) and only check the accounting plumbing."
        )
    if bool(df["usd"].isna().all()):
        st.caption("USD is empty because config/pricing.yaml has no prices.")
else:
    st.info("No LLM usage recorded yet.")
