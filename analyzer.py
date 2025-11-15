import os
import re
import sqlite3
import uuid
from io import BytesIO
from datetime import datetime

import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
import docx

# Configuration 
DB_PATH = "feedback.db"
MODEL_NAME = "gemini-2.5-flash"  

# API Key 
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    st.error("⚠️ GOOGLE_API_KEY not found. Please set it before running the app.\n\nExample:\nexport GOOGLE_API_KEY=\"your_api_key_here\"")
    st.stop()

genai.configure(api_key=API_KEY)

# Database helpers 
def init_db():
    """
    Create the feedback table if it doesn't exist. If table exists, ensure required columns exist.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Create table if not exists with email column
    c.execute("""
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        university TEXT,
        program TEXT,
        created_at TEXT,
        resume_improvements TEXT,
        sop_improvements TEXT,
        lor_improvements TEXT
    )
    """)
    conn.commit()

    expected_cols = {
        "email": "TEXT",
        "university": "TEXT",
        "program": "TEXT",
        "created_at": "TEXT",
        "resume_improvements": "TEXT",
        "sop_improvements": "TEXT",
        "lor_improvements": "TEXT",
    }
    c.execute("PRAGMA table_info(feedback)")
    existing = {row[1]: row for row in c.fetchall()}  

    for col, col_type in expected_cols.items():
        if col not in existing:
            try:
                c.execute(f"ALTER TABLE feedback ADD COLUMN {col} {col_type}")
                conn.commit()
            except Exception:
                pass

    conn.close()

def save_feedback(email, university, program, resume_improv, sop_improv, lor_improv):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO feedback (email, university, program, created_at, resume_improvements, sop_improvements, lor_improvements) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (email, university, program, datetime.utcnow().isoformat(), resume_improv, sop_improv, lor_improv)
    )
    conn.commit()
    conn.close()

def get_last_feedback(email, university, program):
    """
    Return tuple (resume_improv, sop_improv, lor_improv) for latest feedback for this email+university+program.
    If none found, returns (None, None, None)
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT resume_improvements, sop_improvements, lor_improvements
        FROM feedback
        WHERE email=? AND university=? AND program=?
        ORDER BY id DESC LIMIT 1
    """, (email, university, program))
    row = c.fetchone()
    conn.close()
    return row if row else (None, None, None)

# Document extraction
def extract_text(uploaded_file):
    """
    Extract text from PDF, DOCX, or TXT file-like object (Streamlit UploadedFile).
    Returns plain string.
    """
    if not uploaded_file:
        return ""

    name = uploaded_file.name.lower()
    uploaded_file.seek(0)

    # DOCX
    if name.endswith(".docx"):
        try:
            doc = docx.Document(BytesIO(uploaded_file.read()))
            return "\n".join([p.text for p in doc.paragraphs]).strip()
        except Exception:
            return ""

    # PDF
    if name.endswith(".pdf"):
        try:
            reader = PdfReader(uploaded_file)
            pages = []
            for p in reader.pages:
                pages.append(p.extract_text() or "")
            return "\n".join(pages).strip()
        except Exception:
            return ""

    # TXT or fallback
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="ignore")
        return str(raw)
    except Exception:
        return ""

# Prompt builders
def build_initial_prompt(university_name, program_name, resume_text, sop_text, lor_text):
    return f"""
You are an expert University Admissions Evaluator with 15+ years of experience reviewing applications for universities worldwide.
You specialize in analyzing technical and academic profiles for graduate programs.

TARGET UNIVERSITY: {university_name}
TARGET PROGRAM: {program_name}

==============================
RESUME:
{resume_text}
==============================
SOP (Statement of Purpose):
{sop_text}
==============================
LOR (Letter of Recommendation):
{lor_text}
==============================

EVALUATION INSTRUCTIONS:
Analyze each document comprehensively using the criteria below. Be specific, actionable, and constructive in your feedback.

---
### RESUME EVALUATION

EVALUATION CRITERIA:
- ATS Compatibility: Formatting, keywords, parsing-friendly structure
- Technical Relevance: Alignment with target program's requirements
- Presentation: Layout, clarity, professional appearance, quantifiable achievements
- Content Quality: Impact metrics, action verbs, relevance, conciseness

ANALYZE FOR:
1. Format issues (ATS compatibility, fonts, spacing, sections)
2. Missing sections (education, experience, skills, projects, certifications)
3. Weak descriptions (lack of metrics, vague language, passive voice)
4. Relevance gaps (skills/projects not aligned with {program_name})
5. Technical depth (programming languages, tools, technologies for tech programs)
6. Achievement quantification (numbers, percentages, impact)
7. Length appropriateness (1-2 pages for graduate applications)

PROVIDE:
**STRENGTHS:**
- [List 3-5 specific strong points with examples]

**AREAS_OF_IMPROVEMENT:**
- [List 5-8 specific, actionable improvements with reasoning]
- Format: "Issue: [specific problem]. Suggestion: [how to fix it]. Why: [impact on application]."

**SCORES:**
ATS_SCORE: X/100 [Score based on parsing friendliness, keyword optimization]
TECHNICAL_RELEVANCE_SCORE: X/100 [Alignment with {program_name} requirements]
PRESENTATION_SCORE: X/100 [Professional appearance, clarity, achievement quantification]

---
### SOP EVALUATION

EVALUATION CRITERIA:
- Personal Narrative: Authentic story, motivation, passion
- Academic/Research Interest: Clear articulation of research goals
- Program Fit: Specific reasons for choosing this university/program
- Career Goals: Well-defined short-term and long-term objectives
- Writing Quality: Grammar, structure, coherence, conciseness
- Uniqueness: Avoidance of clichés and generic statements

ANALYZE FOR:
1. Opening hook (engaging vs generic)
2. Personal journey (authentic narrative vs template language)
3. Academic preparation (relevant coursework, projects, research)
4. Research interests (specific vs vague, aligned with program)
5. Why this university (specific professors, labs, courses, resources mentioned)
6. Why this program (clear understanding of program strengths)
7. Career goals (realistic, well-articulated, connected to program)
8. Writing issues (grammar errors, redundancy, weak transitions, clichés)
9. Length (typically 500-1000 words for most programs)
10. Red flags (plagiarism indicators, overly emotional language, negative tone)

PROVIDE:
**STRENGTHS:**
- [List 3-5 specific strong points with examples from the text]

**AREAS_OF_IMPROVEMENT:**
- [List 6-10 specific, actionable improvements]
- Format: "Issue: [specific problem with quote if relevant]. Suggestion: [concrete improvement]. Why: [how this strengthens application]."

**SPECIFIC CHECKS:**
- Generic statements to replace: [List any clichés like "passion since childhood", "dream university"]
- Missing elements: [Any crucial missing components]
- Professors/faculty mentioned: [Yes/No - if no, flag as critical improvement]
- Research alignment: [Specific vs vague]

**SCORE:**
SOP_SCORE: X/100 [Overall quality, fit demonstration, writing excellence]

---
### LOR EVALUATION

EVALUATION CRITERIA:
- Recommender Credibility: Title, relationship, observation duration
- Specific Examples: Concrete instances vs generic praise
- Comparative Assessment: How candidate ranks among peers
- Character Insights: Leadership, collaboration, resilience, initiative
- Academic/Professional Skills: Relevant abilities demonstrated
- Authenticity: Genuine voice vs template language

ANALYZE FOR:
1. Recommender qualifications (appropriate authority, relevant position)
2. Relationship context (duration, capacity, credibility)
3. Specific examples (concrete stories vs "excellent student" platitudes)
4. Quantifiable comparisons ("top 5% of students" vs "very good")
5. Skills demonstration (evidence of claimed abilities)
6. Balanced perspective (acknowledges growth areas professionally)
7. Letter structure (introduction, body with examples, strong conclusion)
8. Length (typically 400-600 words)
9. Red flags (overly generic, written by student, lack of specifics)
10. Alignment with resume/SOP (consistent narrative)

PROVIDE:
**STRENGTHS:**
- [List 3-5 specific strong points]

**AREAS_OF_IMPROVEMENT:**
- [List 5-8 specific improvements]
- Format: "Issue: [problem]. Suggestion: [improvement]. Impact: [why this matters]."

**SPECIFIC CHECKS:**
- Specific examples provided: [Count and quality]
- Comparative statements: [Yes/No with examples]
- Generic phrases to replace: [List any "hard-working", "dedicated" without context]
- Recommender credibility: [Assessed strength]

**SCORE:**
LOR_SCORE: X/100 [Credibility, specificity, persuasiveness]

---
### OVERALL ASSESSMENT

**PROFILE_SUMMARY:**
[3-4 sentences summarizing the candidate's overall profile strength, consistency across documents, and unique value proposition]

**COMPETITIVE_ANALYSIS:**
[How this profile compares to typical admits for {program_name} at {university_name}]

**CRITICAL_GAPS:**
[Top 3 most important improvements needed across all documents]

**OVERALL_READINESS_SCORE:** X/100
[Holistic assessment of application readiness]

**FINAL_RECOMMENDATION:**
- Status: [READY TO SUBMIT / MINOR REVISIONS NEEDED / MAJOR REVISIONS REQUIRED]
- Priority Actions: [Top 3-5 actions ranked by impact]
- Timeline Suggestion: [Realistic timeframe for improvements]

SCORING GUIDE:
90-100: Exceptional, competitive for top programs
80-89: Strong, likely competitive with minor improvements
70-79: Good foundation, needs moderate improvements
60-69: Weak areas present, requires significant work
Below 60: Major revisions needed across multiple areas
"""

def build_re_evaluation_prompt(university_name, program_name, resume_text, sop_text, lor_text, prev_feedback):
    return f"""
You are an expert University Admissions Evaluator conducting a RE-EVALUATION of revised application documents.

TARGET UNIVERSITY: {university_name}
TARGET PROGRAM: {program_name}

The applicant previously received detailed feedback and has submitted revised documents. Your task:
1. Methodically check each previous improvement suggestion
2. Assess what was addressed, partially addressed, or ignored
3. Identify any NEW issues introduced in revisions
4. Provide updated scores with justification
5. Give a clear GO/NO-GO recommendation

==============================
PREVIOUS RESUME FEEDBACK:
{prev_feedback.get('resume_improvement', 'NO_PREVIOUS_FEEDBACK')}

REVISED RESUME:
{resume_text}

PREVIOUS SOP FEEDBACK:
{prev_feedback.get('sop_improvement', 'NO_PREVIOUS_FEEDBACK')}

REVISED SOP:
{sop_text}

PREVIOUS LOR FEEDBACK:
{prev_feedback.get('lor_improvement', 'NO_PREVIOUS_FEEDBACK')}

REVISED LOR:
{lor_text}
==============================

RESPOND IN THIS EXACT STRUCTURE:

---
### ACKNOWLEDGED_IMPROVEMENTS

**RESUME:**
Fully Addressed:
- [List each previous issue that was completely resolved with evidence]

Partially Addressed:
- [List issues with some improvement but not complete, explain what's missing]

Not Addressed:
- [List ignored issues that remain unchanged]

**SOP:**
Fully Addressed:
- [List resolved issues with specific examples]

Partially Addressed:
- [List partial improvements and what remains]

Not Addressed:
- [List unchanged issues]

**LOR:**
Fully Addressed:
- [List resolved issues]

Partially Addressed:
- [List partial improvements]

Not Addressed:
- [List ignored suggestions]

---
### NEW_OR_REMAINING_ISSUES

**RESUME:**
New Issues Introduced:
- [Any new problems created during revision]

Critical Remaining Issues:
- [Most important unresolved problems]

Minor Remaining Issues:
- [Less critical items]

**SOP:**
New Issues Introduced:
- [New problems in revised version]

Critical Remaining Issues:
- [Major unresolved items]

Minor Remaining Issues:
- [Less critical items]

**LOR:**
New Issues Introduced:
- [New problems]

Critical Remaining Issues:
- [Major unresolved items]

Minor Remaining Issues:
- [Less critical items]

---
### UPDATED_SCORES

**RESUME:**
- ATS_SCORE: X/100 (Previous: note if improved/declined/same)
- TECHNICAL_RELEVANCE_SCORE: X/100 (Previous comparison)
- PRESENTATION_SCORE: X/100 (Previous comparison)
- Overall Resume Score: X/100

**SOP:**
- SOP_SCORE: X/100 (Previous comparison)

**LOR:**
- LOR_SCORE: X/100 (Previous comparison)

**OVERALL_READINESS_SCORE:** X/100 (Previous comparison)

---
### IMPROVEMENT_TRAJECTORY

**Positive Changes:**
- [List top 3-5 improvements made]

**Regression or No Progress:**
- [List any areas that got worse or showed no improvement]

**Effort Assessment:**
- [Evaluate how thoroughly the applicant addressed feedback]

---
### FINAL_VERDICT

**STATUS:** [Choose ONE]
- âœ… GOOD TO GO: Application is strong and ready for submission
- âš ï¸ MINOR CHANGES NEEDED: 1-2 quick fixes, then ready (< 2 hours work)
- 🔴 SIGNIFICANT CHANGES NEEDED: Major revisions required (> 1 week work)

**REASONING:**
[2-3 sentences explaining the verdict]

**IF MINOR CHANGES NEEDED:**
Priority Actions (in order):
1. [Most critical fix with specific instruction]
2. [Second priority with specific instruction]
3. [Third priority if applicable]

**IF SIGNIFICANT CHANGES NEEDED:**
Critical Issues Blocking Submission:
1. [Most serious problem requiring major work]
2. [Second serious problem]
3. [Third serious problem]

**COMPETITIVE_READINESS:**
[Honest assessment of chances for {program_name} at {university_name}]

**RECOMMENDED_NEXT_STEPS:**
[Specific action plan with timeline]

---

IMPORTANT GUIDELINES:
- Be honest and constructive
- If revisions made things worse, clearly state it
- Recognize genuine effort and improvement
- If ready, give confidence boost; if not, provide clear roadmap
- Compare scores contextually (small improvements in weak areas vs strong areas)
"""

# Parsing helpers 
def _extract_list_items(block_text, label_pattern=None):
    if not block_text:
        return ""
    if label_pattern:
        pat = re.compile(rf"{label_pattern}[:\s]*\n([\s\S]*?)(?:\n[A-Z ]{{2,}}:|\Z)", re.I)
    else:
        pat = re.compile(r"AREAS_OF_IMPROVEMENT[:\s]*\n([\s\S]*?)(?:\n[A-Z ]{2,}:|\Z)", re.I)
    m = pat.search(block_text)
    if not m:
        # fallback: collect lines that look like bullets
        lines = []
        for line in block_text.splitlines():
            if line.strip().startswith("-"):
                lines.append(line.strip().lstrip("-").strip())
        return "\n".join(lines).strip()
    content = m.group(1).strip()
    items = []
    for line in content.splitlines():
        if line.strip().startswith("-"):
            items.append(line.strip().lstrip("-").strip())
        elif line.strip():
            if items:
                items[-1] += " " + line.strip()
    return "\n".join(items).strip()

def extract_areas_of_improvement_from_initial(text):
    sections = {}
    # Resume
    m = re.search(r"### RESUME EVALUATION\s*(.*?)### SOP EVALUATION", text, re.S | re.I)
    if m:
        resume_block = m.group(1)
        sections['resume'] = _extract_list_items(resume_block, label_pattern=r"AREAS_OF_IMPROVEMENT")
    else:
        sections['resume'] = _extract_list_items(text, label_pattern=r"RESUME.*AREAS_OF_IMPROVEMENT")

    # SOP
    m2 = re.search(r"### SOP EVALUATION\s*(.*?)### LOR EVALUATION", text, re.S | re.I)
    if m2:
        sop_block = m2.group(1)
        sections['sop'] = _extract_list_items(sop_block, label_pattern=r"AREAS_OF_IMPROVEMENT")
    else:
        sections['sop'] = _extract_list_items(text, label_pattern=r"SOP.*AREAS_OF_IMPROVEMENT")

    # LOR
    m3 = re.search(r"### LOR EVALUATION\s*(.*?)### OVERALL", text, re.S | re.I)
    if m3:
        lor_block = m3.group(1)
        sections['lor'] = _extract_list_items(lor_block, label_pattern=r"AREAS_OF_IMPROVEMENT")
    else:
        sections['lor'] = _extract_list_items(text, label_pattern=r"LOR.*AREAS_OF_IMPROVEMENT")

    return sections

# Gemini call 
def call_gemini(prompt: str):
    try:
        model = genai.GenerativeModel(MODEL_NAME)
        response = model.generate_content(prompt)

        if hasattr(response, "text") and response.text:
            return response.text
      
        try:
            if hasattr(response, "candidates"):
                return "\n".join([c.content for c in response.candidates if hasattr(c, "content")])
        except Exception:
            pass
        return str(response)
    except Exception as e:
        return f"⚠️ Error calling Gemini: {e}"

# Streamlit Interface
st.set_page_config(page_title="Analyzer", layout="wide")
st.title("Resume Analyzer — Email-linked Feedback")

st.markdown("""
Upload your Resume, SOP, and LOR. Provide an email to save and retrieve feedback for re-evaluation.
- The first run stores 'Areas of Improvement'.
- Subsequent runs (same email + university + program) will compare revised docs to previous feedback.
""")

init_db()

# Inputs
email = st.text_input("📧 Your email (used to store and retrieve feedback)", value="", placeholder="you@example.com")
university_name = st.text_input("🏛️ University Name", placeholder="e.g. University of Oxford")
program_name = st.text_input("🎯 Target Program", placeholder="e.g. MTech in Artificial Intelligence")

resume_file = st.file_uploader("📄 Upload Resume (pdf/docx/txt)", type=["pdf", "docx", "txt"])
sop_file = st.file_uploader("📝 Upload SOP (pdf/docx/txt)", type=["pdf", "docx", "txt"])
lor_file = st.file_uploader("📜 Upload LOR (pdf/docx/txt)", type=["pdf", "docx", "txt"])

# Action
if st.button("🚀 Analyze / Re-evaluate"):
    # basic validation
    if not email:
        st.error("Please enter your email.")
    elif not (university_name and program_name):
        st.error("Please enter university and program.")
    elif not (resume_file and sop_file and lor_file):
        st.error("Please upload Resume, SOP, and LOR.")
    else:
        
        email_norm = email.strip().lower()

       
        with st.spinner("Extracting text from uploaded files..."):
            resume_text = extract_text(resume_file)
            sop_text = extract_text(sop_file)
            lor_text = extract_text(lor_file)

        prev_resume, prev_sop, prev_lor = get_last_feedback(email_norm, university_name.strip(), program_name.strip())

        if not any([prev_resume, prev_sop, prev_lor]):
            # initial analysis
            st.info("Running initial analysis with Gemini...")
            prompt = build_initial_prompt(university_name.strip(), program_name.strip(), resume_text, sop_text, lor_text)
            response_text = call_gemini(prompt)

            st.subheader("🔎 Gemini Analysis (Initial)")
            st.markdown("**Full response:**")
            st.text_area("Full Response", value=response_text, height=420)

            # parse and save areas of improvement
            parsed = extract_areas_of_improvement_from_initial(response_text)
            resume_improv = parsed.get("resume", "") or ""
            sop_improv = parsed.get("sop", "") or ""
            lor_improv = parsed.get("lor", "") or ""

            save_feedback(email_norm, university_name.strip(), program_name.strip(), resume_improv, sop_improv, lor_improv)
            st.success("✅ Initial analysis complete — 'Areas of Improvement' saved to the database for this email.")
        else:
            # re-evaluation
            st.info("Running re-evaluation with Gemini (comparing to previous feedback)...")
            prev_feedback = {
                "resume_improvement": prev_resume or "NO_PREVIOUS",
                "sop_improvement": prev_sop or "NO_PREVIOUS",
                "lor_improvement": prev_lor or "NO_PREVIOUS"
            }
            prompt = build_re_evaluation_prompt(university_name.strip(), program_name.strip(), resume_text, sop_text, lor_text, prev_feedback)
            response_text = call_gemini(prompt)

            st.subheader("🔁 Gemini Re-evaluation")
            st.markdown("**Full re-evaluation response:**")
            st.text_area("Full Re-eval Response", value=response_text, height=420)

            new_resume = None
            new_sop = None
            new_lor = None

            # Try pattern-based parse
            m = re.search(r"### NEW_OR_REMAINING_ISSUES\s*- RESUME:\s*(.*?)\n\s*- SOP:", response_text, re.S | re.I)
            if m:
                new_resume = m.group(1).strip()
            else:
                # try looser parse
                m2 = re.search(r"NEW_OR_REMAINING_ISSUES[\s\S]*?RESUME:\s*(.*?)\n\s*SOP:", response_text, re.I)
                if m2:
                    new_resume = m2.group(1).strip()

            m_sop = re.search(r"### NEW_OR_REMAINING_ISSUES\s*- SOP:\s*(.*?)\n\s*- LOR:", response_text, re.S | re.I)
            if m_sop:
                new_sop = m_sop.group(1).strip()

            m_lor = re.search(r"### NEW_OR_REMAINING_ISSUES\s*- LOR:\s*(.*?)\n\s*### UPDATED_SCORES", response_text, re.S | re.I)
            if m_lor:
                new_lor = m_lor.group(1).strip()

            resume_to_save = new_resume if new_resume else prev_resume
            sop_to_save = new_sop if new_sop else prev_sop
            lor_to_save = new_lor if new_lor else prev_lor

            save_feedback(email_norm, university_name.strip(), program_name.strip(), resume_to_save or "", sop_to_save or "", lor_to_save or "")
            st.success("✅ Re-evaluation saved. Updated issues (if any) stored for this email + program.")

# show previous feedback for convenience 
st.markdown("---")
st.subheader("View last saved feedback for an email + program")

view_email = st.text_input("Email to view (optional)", value="")
view_uni = st.text_input("University to view (optional)", value="")
view_prog = st.text_input("Program to view (optional)", value="")

if st.button("Show last saved feedback"):
    if not (view_email and view_uni and view_prog):
        st.warning("Please provide email, university and program to view saved feedback.")
    else:
        saved = get_last_feedback(view_email.strip().lower(), view_uni.strip(), view_prog.strip())
        if not any(saved):
            st.info("No saved feedback found for that email + university + program.")
        else:
            st.markdown("**Last saved Areas of Improvement:**")
            st.markdown(f"**Resume:**\n```\n{saved[0]}\n```")
            st.markdown(f"**SOP:**\n```\n{saved[1]}\n```")
            st.markdown(f"**LOR:**\n```\n{saved[2]}\n```")
