# main.py
import PyPDF2
import docx
import google.generativeai as genai

# ===================================
# CONFIGURE GEMINI API
# ===================================
GEMINI_API_KEY = "AIzaSyBnG9A6OdzIIJQE1ASn1RpOtYegoNDLhqU"  
genai.configure(api_key=GEMINI_API_KEY)


# ===================================
# HELPER FUNCTIONS
# ===================================

def read_pdf(file):
    reader = PyPDF2.PdfReader(file)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def read_docx(file):
    doc = docx.Document(file)
    text = "\n".join([para.text for para in doc.paragraphs])
    return text


def extract_text(file):
    if file.name.endswith(".pdf"):
        return read_pdf(file)
    elif file.name.endswith(".docx"):
        return read_docx(file)
    else:
        return "Unsupported file format. Please upload a PDF or DOCX."


# ===================================
# ANALYSIS FUNCTION
# ===================================

def analyze_documents(university, branch, resume_text, sop_text, lor_text):
    """Send all data to Gemini for evaluation."""
    prompt = f"""
    You are an expert university admissions officer.

    Evaluate the student's documents for admission to **{university}**, in the **{branch}** program.

    --- RESUME ---
    {resume_text[:2000]}

    --- STATEMENT OF PURPOSE (SOP) ---
    {sop_text[:2000]}

    --- LETTER OF RECOMMENDATION (LOR) ---
    {lor_text[:2000]}

    Please return a structured analysis including:
    1. Overall Evaluation Score (out of 100)
    2. Key Strengths
    3. Weaknesses or areas for improvement
    4. Suitability for {university} ({branch})
    5. Actionable Recommendations
    """

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    return response.text
