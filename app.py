import streamlit as st
import json
from pipeline import run_step1
from scrape_abstracts import scrape_shortlist
from final_report import score_with_abstracts, generate_report

st.set_page_config(page_title="Prior-Art Research Assistant", layout="wide")
st.title("Prior-Art Research Assistant")
st.caption("Describe an invention, get a ranked list of relevant existing patents.")

invention_description = st.text_area(
    "Invention description",
    placeholder="e.g. a wearable device that monitors blood glucose non-invasively using IR spectroscopy",
    height=100
)

if st.button("Run research", type="primary", disabled=not invention_description):
    with st.spinner("Running plan + search + score..."):
        shortlist, log = run_step1(invention_description)

    st.write(f"Shortlisted {len(shortlist)} patents.")

    if log.get("replans"):
        st.warning(f"Agent adapted mid-run: {len(log['replans'])} replan(s) triggered.")
        for r in log["replans"]:
            st.write(f"- Query `{r['original_query']}` failed ({r['reason']}) -> replaced with `{r['replacement_query']}`")

    with open("shortlist.json", "w") as f:
        json.dump(shortlist, f)

    with st.spinner("Scraping abstracts..."):
        scraped = scrape_shortlist(shortlist_path="shortlist.json", output_path="patents_with_abstracts.json")

    with st.spinner("Scoring with full abstracts..."):
        scored_patents = [p for p in scraped if p.get("abstract")]
        ranked = []
        if scored_patents:
            ranked = score_with_abstracts(invention_description, scored_patents)
            ranked.sort(key=lambda p: p["abstract_score"], reverse=True)
            with open("log.json", "w") as f:
                json.dump(log, f)
            generate_report(invention_description, ranked, log_path="log.json", output_path="report.md")

    st.success("Done!")

    st.subheader("Top Relevant Prior Art")
    for p in ranked[:10]:
        if p.get("abstract_score", 0) < 5:
            continue
        with st.container(border=True):
            st.markdown(f"**{p.get('title') or p.get('odp_title')}**")
            st.markdown(f"Score: `{p['abstract_score']}/10`  |  [View on Google Patents]({p.get('url')})")
            st.caption(p.get("abstract_justification", ""))

    if ranked:
        st.subheader("Download outputs")
        col1, col2 = st.columns(2)
        with open("report.md") as f:
            col1.download_button("report.md", f.read(), file_name="report.md")
        with open("shortlist.json") as f:
            col2.download_button("shortlist.json", f.read(), file_name="shortlist.json")
