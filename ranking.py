import os
import json
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from papers_with_code import Paper, Base
from openai import OpenAI
from typing import List
from logger_config import get_logger
from dotenv import load_dotenv

# Get logger for the current module
logger = get_logger(__name__)


def get_random_papers(session, limit: int = 20) -> List[Paper]:
    """Get random unread papers from database."""
    return (
        session.query(Paper)
        .filter_by(thoroughly_read=False)
        .order_by(func.random())
        .limit(limit)
        .all()
    )


def create_prompt(papers: List[Paper]) -> str:
    """Create prompt for ChatGPT with paper information."""
    papers_info = []
    for i, paper in enumerate(papers, 1):
        papers_info.append(
            f"Paper {i}:\n"
            f"ID: {paper.id}\n"
            f"Title: {paper.title}\n"
            f"Abstract: {paper.abstract}\n"
        )

    prompt = (
        "Below are 20 research papers. Please analyze them and select the 3 most interesting "
        "papers based on their potential impact, innovation, and practical applications. "
        "Return only a JSON array containing the IDs of the 3 selected papers in order of "
        "preference. Example format: [123, 456, 789]\n\n"
        f"{'\n'.join(papers_info)}"
    )
    return prompt


def get_chatgpt_ranking(prompt: str) -> List[int]:
    """Get paper rankings from ChatGPT."""
    try:
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.deepseek.com"
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a research paper analyst. Respond only with a JSON array of paper IDs.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=100,
        )

        # Extract the response text
        result = response.choices[0].message.content.strip()

        logger.info(f"ChatGPT response: {result}")

        # Try to parse as JSON first
        try:
            paper_ids = json.loads(result)
            return paper_ids
        except json.JSONDecodeError:
            # If not valid JSON, try to extract numbers
            import re

            numbers = re.findall(r"\d+", result)
            paper_ids = [int(num) for num in numbers[:3]]  # Take first 3 numbers
            logger.warning(f"Failed to parse JSON, extracted numbers: {paper_ids}")
            return paper_ids

    except Exception as e:
        logger.error(f"Error getting ChatGPT ranking: {e}")
        return []


def mark_papers_as_read(session, papers: List[Paper]):
    """Mark papers as thoroughly read."""
    for paper in papers:
        paper.thoroughly_read = True
    session.commit()


def main():
    # Load environment variables from .env file
    load_dotenv()

    # Setup database connection
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get random unread papers
        papers = get_random_papers(session)
        if not papers:
            logger.error("No unread papers found in database")
            return

        # Create prompt and get rankings
        prompt = create_prompt(papers)
        ranked_paper_ids = get_chatgpt_ranking(prompt)

        # Get top 3 papers
        top_papers = []
        logger.info("Top 3 recommended papers:")
        for rank, paper_id in enumerate(ranked_paper_ids, 1):
            paper = session.query(Paper).filter_by(id=paper_id).first()
            if paper:
                top_papers.append(paper)
                logger.info(f"{rank}. [ID: {paper.id}] {paper.title}")
                logger.info(f"   GitHub: {paper.github_link}")
                logger.info(f"   Paper: {paper.paper_link}\n")

        # Mark only top 3 papers as read
        mark_papers_as_read(session, top_papers)
        logger.info(f"Marked {len(top_papers)} top papers as thoroughly read")

    finally:
        session.close()


if __name__ == "__main__":
    main()
