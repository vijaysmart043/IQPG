"""
Bloom RAG Controller - Adapter for integrating bloom_rag.py into Flask.
This module provides a clean interface for the RAG pipeline without modifying
the original bloom_rag.py logic.
"""

import os
import sys
from typing import List, Dict, Generator, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Add RAG directory to path for imports
RAG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'RAG')
if RAG_DIR not in sys.path:
    sys.path.insert(0, RAG_DIR)

from bloom_rag import CohereRAGClient, chunk_text

load_dotenv()

BLOOM_LEVELS = [
    "Remember",
    "Understand",
    "Apply",
    "Analyze",
    "Evaluate",
    "Create"
]


@dataclass
class ChunkResult:
    """Result from processing a single chunk."""
    chunk_index: int
    chunk_text: str
    question: Optional[str]
    error: Optional[str]
    success: bool


@dataclass
class MCQResult:
    """Result from processing a single chunk for MCQ generation."""
    chunk_index: int
    chunk_text: str
    question: Optional[str]
    options: Optional[Dict[str, str]]
    correct_answer: Optional[str]
    error: Optional[str]
    success: bool


@dataclass
class StagedQuestion:
    """A question with unit and sub-question index for staging format."""
    unit_number: int
    question_index: str  # 'a', 'b', 'c', etc.
    question_id: str  # e.g., '1a', '1b', '2a'
    question_text: str
    bloom_level: str
    chunk_text: str
    is_mcq: bool = False
    options: Optional[Dict[str, str]] = None
    correct_answer: Optional[str] = None


def format_staged_questions(questions: List[Dict], is_mcq: bool = False) -> Dict[int, List[StagedQuestion]]:
    """
    Format questions into staged structure with unit-based indexing.
    Returns: {1: [StagedQuestion(1a), StagedQuestion(1b)], 2: [StagedQuestion(2a), ...]}
    """
    staging: Dict[int, List[StagedQuestion]] = {}
    
    for i, q in enumerate(questions):
        unit_number = i + 1  # Each chunk = one unit
        question_index = 'a'  # First question in unit
        
        if unit_number not in staging:
            staging[unit_number] = []
        
        # Determine the next question index for this unit
        existing_count = len(staging[unit_number])
        question_index = chr(ord('a') + existing_count)
        question_id = f"{unit_number}{question_index}"
        
        staged = StagedQuestion(
            unit_number=unit_number,
            question_index=question_index,
            question_id=question_id,
            question_text=q.get('question', ''),
            bloom_level=q.get('bloom_level', ''),
            chunk_text=q.get('chunk_text', ''),
            is_mcq=is_mcq,
            options=q.get('options') if is_mcq else None,
            correct_answer=q.get('correct_answer') if is_mcq else None
        )
        staging[unit_number].append(staged)
    
    return staging


def add_question_to_staging(staging: Dict[int, List[StagedQuestion]], unit_number: int, 
                            question_data: Dict, is_mcq: bool = False) -> StagedQuestion:
    """Add a question to an existing staging structure."""
    if unit_number not in staging:
        staging[unit_number] = []
    
    existing_count = len(staging[unit_number])
    question_index = chr(ord('a') + existing_count)
    question_id = f"{unit_number}{question_index}"
    
    staged = StagedQuestion(
        unit_number=unit_number,
        question_index=question_index,
        question_id=question_id,
        question_text=question_data.get('question', ''),
        bloom_level=question_data.get('bloom_level', ''),
        chunk_text=question_data.get('chunk_text', ''),
        is_mcq=is_mcq,
        options=question_data.get('options') if is_mcq else None,
        correct_answer=question_data.get('correct_answer') if is_mcq else None
    )
    staging[unit_number].append(staged)
    return staged


@dataclass
class RAGConfig:
    """Configuration for RAG pipeline."""
    cohere_api_key: str
    chunk_max_chars: int = 4000
    
    @classmethod
    def from_env(cls) -> 'RAGConfig':
        """Load configuration from environment variables."""
        cohere_key = os.getenv("COHERE_API_KEY")
        if not cohere_key:
            raise ValueError("COHERE_API_KEY environment variable is not set.")
        return cls(cohere_api_key=cohere_key)


class BloomRAGController:
    """
    Controller for Bloom's Taxonomy RAG question generation.
    Wraps the existing CohereRAGClient without modifying its logic.
    """
    
    def __init__(self, config: Optional[RAGConfig] = None):
        """Initialize the controller with optional config."""
        self.config = config or RAGConfig.from_env()
        self._client: Optional[CohereRAGClient] = None
    
    @property
    def client(self) -> CohereRAGClient:
        """Lazy initialization of Cohere client."""
        if self._client is None:
            self._client = CohereRAGClient(api_key=self.config.cohere_api_key)
        return self._client
    
    def chunk_text(self, text: str, max_chars: Optional[int] = None) -> List[str]:
        """
        Chunk text using the existing chunk_text function.
        Uses config max_chars if not specified.
        """
        max_chars = max_chars or self.config.chunk_max_chars
        return chunk_text(text, max_chars=max_chars)
    
    def generate_question_for_chunk(
        self, 
        chunk: str, 
        bloom_level: str
    ) -> str:
        """
        Generate a single Bloom-level question for a chunk.
        Directly calls the existing CohereRAGClient method.
        """
        return self.client.generate_bloom_question(
            context=chunk,
            bloom_level=bloom_level
        )
    
    def process_text_streaming(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Generator[ChunkResult, None, None]:
        """
        Process text and generate questions chunk by chunk.
        Yields results as they complete for real-time progress updates.
        Does NOT stop if one chunk fails.
        """
        chunks = self.chunk_text(text, max_chars)
        
        for i, chunk in enumerate(chunks):
            try:
                question = self.generate_question_for_chunk(chunk, bloom_level)
                yield ChunkResult(
                    chunk_index=i,
                    chunk_text=chunk,
                    question=question,
                    error=None,
                    success=True
                )
            except Exception as e:
                yield ChunkResult(
                    chunk_index=i,
                    chunk_text=chunk,
                    question=None,
                    error=str(e),
                    success=False
                )
    
    def process_text_batch(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Dict:
        """
        Process text and return all results at once.
        Returns a dictionary with results, errors, and statistics.
        """
        chunks = self.chunk_text(text, max_chars)
        results = []
        errors = []
        
        for i, chunk in enumerate(chunks):
            try:
                question = self.generate_question_for_chunk(chunk, bloom_level)
                results.append({
                    'chunk_index': i,
                    'chunk_text': chunk,
                    'question': question
                })
            except Exception as e:
                errors.append({
                    'chunk_index': i,
                    'chunk_text': chunk,
                    'error': str(e)
                })
        
        return {
            'total_chunks': len(chunks),
            'successful': len(results),
            'failed': len(errors),
            'questions': results,
            'errors': errors,
            'bloom_level': bloom_level
        }

    def generate_mcq_for_chunk(self, chunk: str, bloom_level: str) -> Dict:
        """
        Generate a single Bloom-level MCQ for a chunk.
        Returns a dictionary with question, options, and correct_answer.
        """
        return self.client.generate_bloom_mcq(
            context=chunk,
            bloom_level=bloom_level
        )
    
    def process_mcq_streaming(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Generator[MCQResult, None, None]:
        """
        Process text and generate MCQs chunk by chunk.
        Yields MCQResult as they complete for real-time progress updates.
        """
        chunks = self.chunk_text(text, max_chars)
        
        for i, chunk in enumerate(chunks):
            try:
                mcq = self.generate_mcq_for_chunk(chunk, bloom_level)
                yield MCQResult(
                    chunk_index=i,
                    chunk_text=chunk,
                    question=mcq.get('question', ''),
                    options=mcq.get('options', {}),
                    correct_answer=mcq.get('correct_answer', 'A'),
                    error=None,
                    success=True
                )
            except Exception as e:
                yield MCQResult(
                    chunk_index=i,
                    chunk_text=chunk,
                    question=None,
                    options=None,
                    correct_answer=None,
                    error=str(e),
                    success=False
                )
    
    def process_mcq_batch(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Dict:
        """
        Process text and return all MCQ results at once.
        Returns a dictionary with results, errors, and statistics.
        """
        chunks = self.chunk_text(text, max_chars)
        results = []
        errors = []
        
        for i, chunk in enumerate(chunks):
            try:
                mcq = self.generate_mcq_for_chunk(chunk, bloom_level)
                results.append({
                    'chunk_index': i,
                    'chunk_text': chunk,
                    'question': mcq.get('question', ''),
                    'options': mcq.get('options', {}),
                    'correct_answer': mcq.get('correct_answer', 'A'),
                    'bloom_level': bloom_level
                })
            except Exception as e:
                errors.append({
                    'chunk_index': i,
                    'chunk_text': chunk,
                    'error': str(e)
                })
        
        return {
            'total_chunks': len(chunks),
            'successful': len(results),
            'failed': len(errors),
            'mcqs': results,
            'errors': errors,
            'bloom_level': bloom_level
        }
    
    def process_text_staged(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Dict[int, List[StagedQuestion]]:
        """
        Process text and return questions in staged format (1a, 1b, 2a, 2b...).
        Each chunk = one unit, each question within unit gets alphabetic index.
        """
        chunks = self.chunk_text(text, max_chars)
        staging: Dict[int, List[StagedQuestion]] = {}
        
        for i, chunk in enumerate(chunks):
            unit_number = i + 1
            try:
                question = self.generate_question_for_chunk(chunk, bloom_level)
                add_question_to_staging(
                    staging, 
                    unit_number,
                    {
                        'question': question,
                        'bloom_level': bloom_level,
                        'chunk_text': chunk[:200] + '...' if len(chunk) > 200 else chunk
                    },
                    is_mcq=False
                )
            except Exception:
                pass  # Skip failed chunks
        
        return staging
    
    def process_mcq_staged(
        self,
        text: str,
        bloom_level: str,
        max_chars: Optional[int] = None
    ) -> Dict[int, List[StagedQuestion]]:
        """
        Process text and return MCQs in staged format (1a, 1b, 2a, 2b...).
        Each chunk = one unit, each MCQ within unit gets alphabetic index.
        """
        chunks = self.chunk_text(text, max_chars)
        staging: Dict[int, List[StagedQuestion]] = {}
        
        for i, chunk in enumerate(chunks):
            unit_number = i + 1
            try:
                mcq = self.generate_mcq_for_chunk(chunk, bloom_level)
                add_question_to_staging(
                    staging,
                    unit_number,
                    {
                        'question': mcq.get('question', ''),
                        'bloom_level': bloom_level,
                        'chunk_text': chunk[:200] + '...' if len(chunk) > 200 else chunk,
                        'options': mcq.get('options', {}),
                        'correct_answer': mcq.get('correct_answer', 'A')
                    },
                    is_mcq=True
                )
            except Exception:
                pass  # Skip failed chunks
        
        return staging


def get_controller(api_key: Optional[str] = None) -> BloomRAGController:
    """
    Factory function to get a BloomRAGController instance.
    Allows optional API key override.
    """
    if api_key:
        config = RAGConfig(cohere_api_key=api_key)
    else:
        config = RAGConfig.from_env()
    return BloomRAGController(config)


def validate_bloom_level(level: str) -> bool:
    """Validate that a bloom level is valid."""
    return level in BLOOM_LEVELS
