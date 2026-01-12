"""
Simple RAG pipeline for Bloom's Taxonomy question generation using:
- Cohere (embeddings + question generation)
- Pinecone (vector database)

Installation (run in your terminal):

    pip install cohere pinecone python-dotenv

Environment variables (set these before running):

    # macOS / Linux (bash)
    export COHERE_API_KEY="your_cohere_api_key"
    export PINECONE_API_KEY="your_pinecone_api_key"
    export PINECONE_ENVIRONMENT="your_pinecone_environment"

    # Windows (PowerShell)
    setx COHERE_API_KEY "your_cohere_api_key"
    setx PINECONE_API_KEY "your_pinecone_api_key"
    setx PINECONE_ENVIRONMENT "your_pinecone_environment"

Supported Bloom's Taxonomy levels (input as plain text, case-insensitive):
- Remember
- Understand
- Apply
- Analyze
- Evaluate
- Create
"""

import os
from typing import List

from dotenv import load_dotenv
import cohere
import pinecone


COHERE_EMBEDDING_MODEL = "embed-english-v3.0"
COHERE_GENERATION_MODEL = "command-r-08-2024"
EMBEDDING_DIMENSION = 1024
PINECONE_INDEX_NAME = "bloom-rag-index"


def chunk_text(text: str, max_chars: int = 500) -> List[str]:
    """
    Simple whitespace-based text chunker.
    """
    words = text.split()
    chunks: List[str] = []
    current_words: List[str] = []
    current_length = 0

    for word in words:
        word_length = len(word) + (1 if current_words else 0)
        if current_length + word_length > max_chars:
            chunks.append(" ".join(current_words))
            current_words = [word]
            current_length = len(word)
        else:
            current_words.append(word)
            current_length += word_length

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


class CohereRAGClient:
    """
    Wraps Cohere for embeddings and Bloom-level question generation.
    """

    def __init__(self, api_key: str):
        self.client = cohere.Client(api_key)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Returns embedding vectors for the input texts.
        """
        if not texts:
            return []

        response = self.client.embed(
            texts=texts,
            model=COHERE_EMBEDDING_MODEL,
        )
        return response.embeddings

    def generate_bloom_question(self, context: str, bloom_level: str) -> str:
        """
        Generates one Bloom-level-aligned question from the given context.
        """
        prompt = f"""
You are an educational AI assistant that writes high-quality assessment questions.

You will be given:
1) A piece of source learning material.
2) A Bloom's Taxonomy cognitive level.

Your job is to write exactly ONE question that:
- Aligns with the requested Bloom's Taxonomy level.
- Uses only the information from the source material.
- Is clear and grammatically correct.
- Does NOT mention Bloom's Taxonomy or cognitive levels.
- Does NOT include the answer or any explanation.
- Is phrased as a single, standalone question.

Source learning material:
\"\"\"{context}\"\"\"

Requested Bloom's Taxonomy level:
\"\"\"{bloom_level}\"\"\"

Now write the question.

Question:
""".strip()

        response = self.client.chat(
            model=COHERE_GENERATION_MODEL,
            message=prompt,
            max_tokens=128,
            temperature=0.7,
        )

        raw_text = response.text.strip()
        cleaned = raw_text.lstrip("-•").strip()
        return cleaned

    def generate_bloom_mcq(self, context: str, bloom_level: str) -> dict:
        """
        Generates one Bloom-level-aligned MCQ from the given context.
        Returns a dictionary with question, options (A, B, C, D), and correct_answer.
        """
        prompt = f"""
You are an educational AI assistant that creates high-quality multiple-choice questions.

You will be given:
1) A piece of source learning material.
2) A Bloom's Taxonomy cognitive level.

Your job is to create exactly ONE multiple-choice question that:
- Aligns with the requested Bloom's Taxonomy level.
- Uses only the information from the source material.
- Has exactly 4 options labeled A, B, C, D.
- Has exactly ONE correct answer.
- Has plausible distractors (wrong options should be believable but clearly incorrect).
- Does NOT mention Bloom's Taxonomy or cognitive levels.
- Is clear and grammatically correct.

Source learning material:
\"\"\"{context}\"\"\"

Requested Bloom's Taxonomy level:
\"\"\"{bloom_level}\"\"\"

Output format (follow exactly):
QUESTION: [Your question here]
A) [Option A]
B) [Option B]
C) [Option C]
D) [Option D]
CORRECT: [Letter of correct answer]

Now create the MCQ.
""".strip()

        response = self.client.chat(
            model=COHERE_GENERATION_MODEL,
            message=prompt,
            max_tokens=300,
            temperature=0.7,
        )

        raw_text = response.text.strip()
        return self._parse_mcq_response(raw_text)

    def _parse_mcq_response(self, text: str) -> dict:
        """
        Parses the MCQ response from Cohere into a structured dictionary.
        """
        import re
        
        result = {
            "question": "",
            "options": {"A": "", "B": "", "C": "", "D": ""},
            "correct_answer": "A"
        }
        
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Parse question
            if line.upper().startswith('QUESTION:'):
                result["question"] = line[9:].strip()
            # Parse options
            elif line.startswith('A)') or line.startswith('A.'):
                result["options"]["A"] = line[2:].strip()
            elif line.startswith('B)') or line.startswith('B.'):
                result["options"]["B"] = line[2:].strip()
            elif line.startswith('C)') or line.startswith('C.'):
                result["options"]["C"] = line[2:].strip()
            elif line.startswith('D)') or line.startswith('D.'):
                result["options"]["D"] = line[2:].strip()
            # Parse correct answer
            elif line.upper().startswith('CORRECT:'):
                answer = line[8:].strip().upper()
                if answer in ['A', 'B', 'C', 'D']:
                    result["correct_answer"] = answer
        
        # Fallback: if question not found with prefix, use first non-option line
        if not result["question"]:
            for line in lines:
                line = line.strip()
                if line and not any(line.startswith(p) for p in ['A)', 'B)', 'C)', 'D)', 'A.', 'B.', 'C.', 'D.', 'CORRECT:']):
                    if not line.upper().startswith('QUESTION:'):
                        result["question"] = line
                        break
        
        return result


def init_pinecone(api_key: str) -> pinecone.Pinecone:
    """
    Creates a Pinecone client instance.
    """
    client = pinecone.Pinecone(api_key=api_key)
    return client


def get_or_create_index(
    client: pinecone.Pinecone,
    index_name: str,
    dimension: int,
    environment: str,
):
    """
    Returns an existing Pinecone index, or creates it if needed.
    """
    existing_indexes = client.list_indexes()
    existing_names = [idx.name for idx in existing_indexes]
    if index_name not in existing_names:
        client.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=pinecone.ServerlessSpec(
                cloud="aws",
                region=environment,
            ),
        )
    return client.Index(index_name)


def ingest_text(
    text: str,
    cohere_client: CohereRAGClient,
    index,
    namespace: str | None = None,
) -> List[str]:
    """
    Chunks text, embeds chunks, and upserts vectors into Pinecone.
    """
    chunks = chunk_text(text)
    if not chunks:
        return []

    embeddings = cohere_client.embed_texts(chunks)

    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vector_id = f"chunk-{i}"
        metadata = {"text": chunk}
        vectors.append((vector_id, embedding, metadata))

    if namespace:
        index.upsert(vectors=vectors, namespace=namespace)
    else:
        index.upsert(vectors=vectors)
    return chunks


def retrieve_relevant_chunks(
    query: str,
    cohere_client: CohereRAGClient,
    index,
    top_k: int = 3,
    namespace: str | None = None,
) -> List[str]:
    """
    Retrieves top-k relevant chunks from Pinecone for the query.
    """
    query_embedding = cohere_client.embed_texts([query])[0]

    query_kwargs = {
        "vector": query_embedding,
        "top_k": top_k,
        "include_metadata": True,
    }
    if namespace:
        query_kwargs["namespace"] = namespace

    results = index.query(**query_kwargs)

    chunks: List[str] = []
    for match in results.get("matches", []):
        metadata = match.get("metadata") or {}
        text = metadata.get("text")
        if text:
            chunks.append(text)

    return chunks


def build_context_from_chunks(chunks: List[str]) -> str:
    """
    Joins retrieved chunks into a single context string.
    """
    if not chunks:
        return ""
    return "\n\n".join(chunks)


def read_multiline_input(prompt: str) -> str:
    """
    Reads multiline text until an empty line is entered.
    """
    print(prompt)
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> None:
    """
    End-to-end RAG demo for Bloom-level question generation.
    """
    load_dotenv()

    cohere_api_key = os.getenv("COHERE_API_KEY")
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    pinecone_environment = os.getenv("PINECONE_ENVIRONMENT")

    if not cohere_api_key:
        raise ValueError("COHERE_API_KEY environment variable is not set.")
    if not pinecone_api_key:
        raise ValueError("PINECONE_API_KEY environment variable is not set.")
    if not pinecone_environment:
        raise ValueError("PINECONE_ENVIRONMENT environment variable is not set.")

    print("=== Bloom's Taxonomy RAG Question Generator ===\n")

    source_text = read_multiline_input(
        "Paste the source learning text, then press Enter on an empty line to finish:"
    )
    if not source_text:
        print("No source text provided. Exiting.")
        return

    bloom_level = input(
        "\nEnter Bloom's Taxonomy level "
        "(Remember, Understand, Apply, Analyze, Evaluate, Create): "
    ).strip()

    query = input(
        "\nOptionally, enter a short query/topic to focus the question\n"
        "(or press Enter to use a generic focus): "
    ).strip()

    if not query:
        query = "Generate a question based on the main ideas of the text."

    print("\nInitializing Cohere client...")
    cohere_client = CohereRAGClient(api_key=cohere_api_key)

    print("Initializing Pinecone and index...")
    pc = init_pinecone(api_key=pinecone_api_key)
    index = get_or_create_index(
        client=pc,
        index_name=PINECONE_INDEX_NAME,
        dimension=EMBEDDING_DIMENSION,
        environment=pinecone_environment,
    )

    print("Chunking and indexing source text...")
    ingest_text(source_text, cohere_client, index)

    print("Retrieving relevant context for the query...")
    retrieved_chunks = retrieve_relevant_chunks(
        query=query,
        cohere_client=cohere_client,
        index=index,
        top_k=3,
    )

    if retrieved_chunks:
        context = build_context_from_chunks(retrieved_chunks)
    else:
        context = source_text

    print("Generating Bloom-level question with Cohere...")
    question = cohere_client.generate_bloom_question(
        context=context,
        bloom_level=bloom_level,
    )

    print("\n=== Generated Question ===")
    print(question)
    print("==========================")


if __name__ == "__main__":
    main()
