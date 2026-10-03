t · PY
"""Text-to-SQL module: lets the RAG chatbot answer questions from SQL databases."""
from .router import route_question, api_router
from .service import answer_sql_question
 
__all__ = ["route_question", "answer_sql_question", "api_router"]