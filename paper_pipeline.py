import os
import json
import yaml  # Add YAML import
from datetime import datetime
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from logger_config import get_logger

# Import project modules
from papers_with_code import (
    Base,
    Paper,
    scrape_papers_with_pagination,
    save_papers_to_db,
)
from ranking import get_random_papers, get_chatgpt_ranking, create_prompt
from get_pdf import download_pdf
from get_markdown_doc2x import convert_to_markdown as convert_to_markdown_doc2x
from get_markdown_mistral import convert_to_markdown as convert_to_markdown_mistral
from summarize_paper import summarize_paper

# Get logger for the current module
logger = get_logger(__name__)


# Load configuration
def load_config():
    try:
        with open("config.yaml", "r") as config_file:
            return yaml.safe_load(config_file)
    except Exception as e:
        logger.error(f"Error loading config.yaml: {str(e)}")
        # Return default configuration
        return {
            "paper_fetch": {"limit": 30},
            "paper_ranking": {"default_limit": 3, "fallback_limit": 1},
            "pdf_to_markdown": {"converter": "mistral_ocr"},
            "output_dir": "./data",
        }


# Global config
config = load_config()


# Simple data class to store paper information
class PaperInfo:
    def __init__(
        self, id, title, github_link, paper_link, code_link, stars, arxiv_link=None
    ):
        self.id = id
        self.title = title
        self.github_link = github_link
        self.paper_link = paper_link
        self.code_link = code_link
        self.stars = stars
        self.arxiv_link = arxiv_link


@contextmanager
def session_scope():
    """Creates a context manager for database sessions to ensure proper handling"""
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def setup_database():
    """Set up and return a database session (legacy function, use session_scope instead)"""
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def fetch_latest_papers(limit=100):
    """Fetch latest papers and save to database"""
    logger.info("Starting to fetch latest papers...")
    base_url = "https://paperswithcode.com/latest"
    papers = scrape_papers_with_pagination(base_url, target_count=limit)

    with session_scope() as session:
        new_count, updated_count = save_papers_to_db(papers, session)
        logger.info(f"New papers added: {new_count}")
        logger.info(f"Papers updated: {updated_count}")
        total_count = session.query(Paper).count()
        logger.info(f"Total papers in database: {total_count}")

    return new_count + updated_count


def rank_and_select_papers(limit=3):
    """Rank papers and select the top papers, up to the specified limit"""
    logger.info("Starting paper ranking...")

    with session_scope() as session:
        papers = get_random_papers(session)
        if not papers:
            logger.error("No unread papers in the database")
            return []

        prompt = create_prompt(papers)
        ranked_paper_ids = get_chatgpt_ranking(prompt)

        # Check if we got paper IDs
        if not ranked_paper_ids:
            logger.error("Ranking process didn't return any paper IDs")
            return []

        # Ensure we only process valid paper IDs
        valid_ids = [pid for pid in ranked_paper_ids if isinstance(pid, int)][:limit]

        top_papers = []
        logger.info("Top recommended papers:")

        for rank, paper_id in enumerate(valid_ids, 1):
            paper = session.query(Paper).filter_by(id=paper_id).first()
            if paper:
                # Create a PaperInfo object with all necessary data
                paper_info = PaperInfo(
                    id=paper.id,
                    title=paper.title,
                    github_link=paper.github_link,
                    paper_link=paper.paper_link,
                    code_link=paper.code_link,
                    stars=paper.stars,
                    arxiv_link=paper.arxiv_link,
                )

                top_papers.append(paper_info)
                logger.info(f"{rank}. [ID: {paper.id}] {paper.title}")
                logger.info(f"   GitHub: {paper.github_link}")
                logger.info(f"   Paper: {paper.arxiv_link or paper.paper_link}\n")

                # Mark paper as read
                paper.thoroughly_read = True

    return top_papers


def get_latest_pdf():
    """Helper function to get the most recently downloaded PDF file"""
    pdf_files = [f for f in os.listdir(".") if f.endswith(".pdf")]
    if not pdf_files:
        return None
    # Sort by modification time, get the latest PDF
    return sorted(pdf_files, key=lambda x: os.path.getmtime(x), reverse=True)[0]


def process_paper(paper_info):
    """Process a single paper: download PDF, convert to Markdown, summarize"""
    logger.info(f"Starting to process paper: {paper_info.title}")

    # Use arXiv link if available, otherwise use paper_link
    paper_url = (
        paper_info.arxiv_link if paper_info.arxiv_link else paper_info.paper_link
    )

    # Download PDF
    if not paper_url:
        logger.error("Paper has no available PDF link")
        return None

    logger.info(f"Downloading paper PDF: {paper_url}")
    try:
        output_dir = config.get("output_dir", "./data")
        download_result = download_pdf(paper_url, output_file_dir=output_dir)

        # Unpack results - now returns (filename, arxiv_url)
        if isinstance(download_result, tuple) and len(download_result) == 2:
            latest_pdf, arxiv_url = download_result
        else:
            # Backward compatibility with old version
            latest_pdf = download_result
            arxiv_url = None

        if not latest_pdf:
            logger.error("Downloaded PDF file not found")
            return None

        latest_pdf = os.path.join(output_dir, latest_pdf)
        # Convert to Markdown based on configuration
        logger.info(f"Converting PDF to Markdown: {latest_pdf}")

        # Get converter from config
        converter = config.get("pdf_to_markdown", {}).get("converter", "mistral_ocr")

        if converter == "doc2x":
            logger.info("Using doc2x for PDF to Markdown conversion")
            convert_to_markdown_doc2x(latest_pdf)

            # Extract content from result.json for doc2x
            try:
                with open("result.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    pages_info = data["pages"]

                # Concatenate all markdown content
                content = "".join(page["md"] for page in pages_info)
            except Exception as e:
                logger.error(f"Error processing doc2x output: {str(e)}")
                return None

        else:  # Default to mistral_ocr
            logger.info("Using Mistral OCR for PDF to Markdown conversion")
            convert_to_markdown_mistral(latest_pdf)

            # Process Mistral OCR response
            try:
                with open("result.json", "r", encoding="utf-8") as f:
                    ocr_response = json.load(f)
                # Concatenate all markdown content from Mistral OCR pages
                content = "".join(
                    page["markdown"]
                    for page in ocr_response["pages"]
                    if page["markdown"]
                )
            except Exception as e:
                logger.error(f"Error processing Mistral OCR output: {str(e)}")
                return None

        # Prefer arXiv link in the following order:
        # 1. arXiv URL from download
        # 2. arXiv link from database
        # 3. Original paper link
        paper_link_to_use = arxiv_url or paper_info.arxiv_link or paper_info.paper_link

        # Add paper metadata
        paper_metadata = f"""
# {paper_info.title}

## Metadata
- **GitHub**: {paper_info.github_link}
- **Paper**: {paper_link_to_use}
- **Code**: {paper_info.code_link}
- **Stars**: {paper_info.stars}

"""
        content = paper_metadata + content

        # Call summarize function
        summary = summarize_paper(content)

        # Save summary
        date = datetime.now().strftime("%Y-%m-%d")
        filename = f"summary_{paper_info.id}_{date}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(summary)

        logger.info(f"Paper summary saved to: {filename}")
        return filename

    except Exception as e:
        logger.error(f"Error downloading PDF: {str(e)}")

    return None


def write_digest_report(summary_files):
    """Generate a summary report from the processed papers"""
    if not summary_files:
        logger.info("No paper summaries were generated, pipeline complete")
        return False

    date = datetime.now().strftime("%Y-%m-%d")
    output_file = f"paper_digest_{date}.md"

    try:
        with open(output_file, "w", encoding="utf-8") as report:
            report.write(f"# Paper Digest Summary - {date}\n\n")

            for summary_file in summary_files:
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_content = f.read()

                    report.write(summary_content)
                    report.write("\n\n---\n\n")  # Separator
                except Exception as e:
                    logger.error(f"Error reading summary file {summary_file}: {str(e)}")

        logger.info(f"Summary report generated: {output_file}")
        return True
    except Exception as e:
        logger.error(f"Error creating digest report: {str(e)}")
        return False


def main():
    """Main pipeline function"""
    load_dotenv()  # Load environment variables

    # Load configuration from YAML file
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
            paper_fetch_limit = config.get("paper_fetch", {}).get("limit", 100)
            default_ranking_limit = config.get("paper_ranking", {}).get(
                "default_limit", 3
            )
            fallback_ranking_limit = config.get("paper_ranking", {}).get(
                "fallback_limit", 1
            )
            logger.info(f"Loaded configuration: paper_fetch_limit={paper_fetch_limit}")
    except Exception as e:
        logger.warning(f"Failed to load configuration from {config_path}: {str(e)}")
        logger.warning("Using default values")
        paper_fetch_limit = 100
        default_ranking_limit = 3
        fallback_ranking_limit = 1

    # Step 1: Get latest papers
    paper_count = fetch_latest_papers(limit=paper_fetch_limit)

    # Step 2: Rank papers and make selection
    with session_scope() as session:
        # Check if there are any unread papers in the database
        unread_papers_exist = (
            session.query(Paper).filter_by(thoroughly_read=False).first() is not None
        )

    if paper_count == 0 and not unread_papers_exist:
        logger.info(
            "No new papers and all existing papers have been read, pipeline complete"
        )
        return

    # When no new papers, limit to just 1 most interesting paper
    limit = fallback_ranking_limit if paper_count == 0 else default_ranking_limit
    top_papers = rank_and_select_papers(limit=limit)

    if not top_papers:
        logger.info("No papers worth reading were selected, pipeline complete")
        return

    if paper_count == 0 and top_papers:
        logger.info(
            f"Selected 1 most interesting paper from database: {top_papers[0].title}"
        )

    # Step 3: Process selected papers
    summary_files = [
        summary_file for paper in top_papers if (summary_file := process_paper(paper))
    ]

    # Step 4: Generate summary report
    write_digest_report(summary_files)


if __name__ == "__main__":
    main()
