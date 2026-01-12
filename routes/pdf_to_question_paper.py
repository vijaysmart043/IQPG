"""
PDF to Question Paper Generator - Using Cohere via Bloom RAG
"""
import os
import sys
from pypdf import PdfReader

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from routes.bloom_rag_controller import get_controller, BLOOM_LEVELS


def extract_pdf_text(pdf_path):
    """Extract all text from a PDF file"""
    reader = PdfReader(pdf_path)
    full_text = []

    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text.append(text)

    return "\n".join(full_text)


def generate_question_paper(pdf_text, cohere_api_key=None):
    """Generate question paper using Cohere via Bloom RAG"""
    
    if not cohere_api_key:
        cohere_api_key = os.getenv("COHERE_API_KEY")
    
    if not cohere_api_key:
        raise ValueError("COHERE_API_KEY is not set. Please provide it or set it in .env file.")
    
    controller = get_controller(cohere_api_key)
    
    # Chunk the text
    chunks = controller.chunk_text(pdf_text, max_chars=4000)
    
    # Generate questions for each unit
    question_paper = []
    bloom_levels = ["Remember", "Understand", "Apply", "Analyze", "Evaluate"]
    
    # Generate 5 units worth of questions
    for unit_num in range(1, 6):
        unit_questions = []
        unit_questions.append(f"\nUNIT-{['I', 'II', 'III', 'IV', 'V'][unit_num-1]}")
        
        # Get chunk for this unit
        chunk_idx = min(unit_num - 1, len(chunks) - 1)
        chunk = chunks[chunk_idx] if chunks else pdf_text[:4000]
        
        try:
            # Generate question 1a
            q1a = controller.generate_question_for_chunk(chunk, bloom_levels[unit_num % len(bloom_levels)])
            unit_questions.append(f"1 a) {q1a} [7M]")
            
            # Generate question 1b
            q1b = controller.generate_question_for_chunk(chunk, bloom_levels[(unit_num + 1) % len(bloom_levels)])
            unit_questions.append(f"   b) {q1b} [7M]")
            
            unit_questions.append("  (OR)")
            
            # Generate question 2a
            q2a = controller.generate_question_for_chunk(chunk, bloom_levels[(unit_num + 2) % len(bloom_levels)])
            unit_questions.append(f"2 a) {q2a} [7M]")
            
            # Generate question 2b
            q2b = controller.generate_question_for_chunk(chunk, bloom_levels[(unit_num + 3) % len(bloom_levels)])
            unit_questions.append(f"   b) {q2b} [7M]")
            
        except Exception as e:
            print(f"Error generating questions for Unit {unit_num}: {e}")
            unit_questions.append(f"[Error generating questions: {e}]")
        
        question_paper.extend(unit_questions)
    
    return "\n".join(question_paper)


def main():
    pdf_path = "syllabus.pdf"
    output_file = "question_paper.txt"

    print("Extracting PDF text...")
    pdf_text = extract_pdf_text(pdf_path)

    print("Generating question paper using Cohere...")
    question_paper = generate_question_paper(pdf_text)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(question_paper)

    print(f"Question paper generated successfully: {output_file}")


if __name__ == "__main__":
    main()
