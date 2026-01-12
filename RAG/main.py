"""
Simple RAG pipeline for Bloom's Taxonomy question generation using:
- Cohere (embeddings + question generation)
- Pinecone (vector database)

Installation (run in your terminal):

    pip install cohere pinecone-client

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

import cohere
import pinecone


# Cohere embedding model used for vectorization
COHERE_EMBEDDING_MODEL = "embed-english-v3.0"

# Cohere text-generation model used for question generation
COHERE_GENERATION_MODEL = "command"

# Embedding dimension for embed-english-v3.0 (fixed by the model)
EMBEDDING_DIMENSION = 1024

# Pinecone index name (can be changed if needed)
PINECONE_INDEX_NAME = "bloom-rag-index"


def chunk_text(text: str, max_chars: int = 500) -> List[str]:
    """
    Very simple whitespace-based text chunker.

    Splits the input text into chunks of up to max_chars characters.
    This keeps chunks small enough for efficient embedding and retrieval.
    """
    words = text.split()
    chunks: List[str] = []
    current_words: List[str] = []
    current_length = 0

    for word in words:
        # +1 accounts for the space between words
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
    Wraps Cohere functionality for embeddings and Bloom-level question generation.
    """

    def __init__(self, api_key: str):
        self.client = cohere.Client(api_key)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Returns a list of embedding vectors for the input texts.
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
        Uses Cohere's 'command' model to generate exactly one question that
        aligns with the requested Bloom's Taxonomy level, using only the
        provided context.
        """
        # We rely entirely on prompt engineering to control Bloom level behavior.
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

        response = self.client.generate(
            model=COHERE_GENERATION_MODEL,
            prompt=prompt,
            max_tokens=128,
            temperature=0.7,
        )

        # Extract and clean the generated question text
        raw_text = response.generations[0].text.strip()
        # Sometimes models prepend bullets or dashes; remove simple leading markers.
        cleaned = raw_text.lstrip("-•").strip()
        return cleaned


def init_pinecone(api_key: str, environment: str) -> None:
    """
    Initializes Pinecone with the provided API key and environment.
    """
    pinecone.init(api_key=api_key, environment=environment)


def get_or_create_index(index_name: str, dimension: int) -> pinecone.index.Index:
    """
    Returns an existing Pinecone index, or creates it if it does not exist.
    """
    existing_indexes = pinecone.list_indexes()
    if index_name not in existing_indexes:
        pinecone.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
        )
    return pinecone.Index(index_name)


def ingest_text(
    text: str,
    cohere_client: CohereRAGClient,
    index: pinecone.index.Index,
) -> List[str]:
    """
    Chunks the text, embeds each chunk, and upserts the resulting vectors into Pinecone.
    Returns the list of chunks for reference.
    """
    chunks = chunk_text(text)
    if not chunks:
        return []

    embeddings = cohere_client.embed_texts(chunks)

    # Prepare vectors for upsert: (id, embedding, metadata)
    vectors = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        vector_id = f"chunk-{i}"
        metadata = {"text": chunk}
        vectors.append((vector_id, embedding, metadata))

    index.upsert(vectors=vectors)
    return chunks


def retrieve_relevant_chunks(
    query: str,
    cohere_client: CohereRAGClient,
    index: pinecone.index.Index,
    top_k: int = 3,
) -> List[str]:
    """
    Retrieves the top-k most relevant text chunks from Pinecone based on the query.
    """
    query_embedding = cohere_client.embed_texts([query])[0]

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
    )

    chunks: List[str] = []
    for match in results.get("matches", []):
        metadata = match.get("metadata") or {}
        text = metadata.get("text")
        if text:
            chunks.append(text)

    return chunks


def build_context_from_chunks(chunks: List[str]) -> str:
    """
    Concatenates retrieved chunks into a single context string.
    """
    if not chunks:
        return ""
    return "\n\n".join(chunks)


def read_multiline_input(prompt: str) -> str:
    """
    Reads multiline text from stdin until an empty line is entered.
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
    Demonstrates end-to-end RAG execution for Bloom-level question generation:
    - Reads source text from the user.
    - Reads a Bloom level and a query focus.
    - Indexes chunks into Pinecone.
    - Retrieves relevant chunks for the query.
    - Asks Cohere to generate one question at the requested Bloom level.
    """
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

    # The query can be a topic, concept, or simple description of focus.
    query = input(
        "\nOptionally, enter a short query/topic to focus the question\n"
        "(or press Enter to use a generic focus): "
    ).strip()

    if not query:
        query = "Generate a question based on the main ideas of the text."

    print("\nInitializing Cohere client...")
    cohere_client = CohereRAGClient(api_key=cohere_api_key)

    print("Initializing Pinecone and index...")
    init_pinecone(api_key=pinecone_api_key, environment=pinecone_environment)
    index = get_or_create_index(
        index_name=PINECONE_INDEX_NAME,
        dimension=EMBEDDING_DIMENSION,
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
        # Fallback: use the full source text if retrieval returns nothing
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