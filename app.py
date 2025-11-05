# app.py
import streamlit as st
from main import extract_text, analyze_documents

# =============================
# STREAMLIT PAGE CONFIG
# =============================

st.set_page_config(
    page_title="AI Admission Document Analyzer 🎓",
    page_icon="🎯",
    layout="centered"
)

# =============================
# PAGE UI
# =============================
st.title("🎓 AI Admission Document Analyzer")
st.markdown("""
Upload your **Resume**, **SOP**, and **LOR**,  
and our AI (powered by Google Gemini) will evaluate your profile for a specific university program.
""")

# --- INPUT FIELDS ---
university = st.text_input("🏫 Enter University Name", placeholder="e.g., Stanford University")
branch = st.text_input("🎯 Enter Branch of Study", placeholder="e.g., Computer Science")

# --- FILE UPLOADS ---
resume_file = st.file_uploader("📄 Upload Resume (.pdf or .docx)", type=["pdf", "docx"])
sop_file = st.file_uploader("📝 Upload Statement of Purpose (.pdf or .docx)", type=["pdf", "docx"])
lor_file = st.file_uploader("💬 Upload Letter of Recommendation (.pdf or .docx)", type=["pdf", "docx"])

# --- ANALYZE BUTTON ---
if st.button("🚀 Analyze My Documents"):
    if not (university and branch and resume_file and sop_file and lor_file):
        st.error("Please fill in all fields and upload all required documents.")
    else:
        with st.spinner("Analyzing your documents... Please wait ⏳"):
            resume_text = extract_text(resume_file)
            sop_text = extract_text(sop_file)
            lor_text = extract_text(lor_file)

            result = analyze_documents(university, branch, resume_text, sop_text, lor_text)

        st.success("✅ Analysis Complete!")
        st.subheader("📊 AI Evaluation Result")
        st.markdown(result)
