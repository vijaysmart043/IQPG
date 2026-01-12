import streamlit as st
import os
from pypdf import PdfReader
from dotenv import load_dotenv
from bloom_rag import CohereRAGClient, chunk_text

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Bloom's Taxonomy Question Generator", page_icon="📚")

st.title("📚 Bloom's Taxonomy Question Generator")
st.write("Upload a PDF to extract text and generate questions using Cohere.")

# API Key handling
api_key = os.getenv("COHERE_API_KEY")
if not api_key:
    api_key = st.text_input("Enter your Cohere API Key:", type="password")
    if not api_key:
        st.warning("Please enter your Cohere API Key to proceed.")
        st.stop()

# Initialize Cohere Client
try:
    cohere_client = CohereRAGClient(api_key=api_key)
except Exception as e:
    st.error(f"Failed to initialize Cohere client: {e}")
    st.stop()

# File Upload
uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")

if uploaded_file is not None:
    try:
        # Extract text from PDF
        reader = PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        st.success("Text extracted successfully!")
        
        # Display extracted text (collapsible)
        with st.expander("View Extracted Text"):
            st.text_area("Extracted Text", text, height=300)

        # Question Generation Section
        st.divider()
        st.subheader("Generate Questions")

        bloom_levels = [
            "Remember",
            "Understand",
            "Apply",
            "Analyze",
            "Evaluate",
            "Create"
        ]
        
        selected_level = st.selectbox("Select Bloom's Taxonomy Level:", bloom_levels)
        
        if st.button("Generate Questions"):
            with st.spinner("Processing text and generating questions..."):
                try:
                    # Chunk text into 4000 character segments
                    chunks = chunk_text(text, max_chars=4000)
                    st.write(f"Splitting text into {len(chunks)} chunks of ~4000 characters each.")
                    
                    progress_bar = st.progress(0)
                    questions_container = st.container()
                    
                    for i, chunk in enumerate(chunks):
                        try:
                            # Update progress
                            progress_bar.progress((i + 1) / len(chunks))
                            
                            # Generate question for this chunk
                            question = cohere_client.generate_bloom_question(chunk, selected_level)
                            
                            # Display result immediately
                            with questions_container:
                                st.markdown(f"**Question {i+1} (from Chunk {i+1}):**")
                                st.info(question)
                                
                        except Exception as e:
                            st.error(f"Error generating question for chunk {i+1}: {e}")
                            
                    st.success("Generation complete!")
                    
                except Exception as e:
                    st.error(f"Error in processing: {e}")

    except Exception as e:
        st.error(f"Error reading PDF: {e}")
