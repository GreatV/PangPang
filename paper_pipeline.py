import os
from datetime import datetime
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
from get_markdown import main as convert_to_markdown
from summarize_paper import summarize_paper

# Get logger for the current module
logger = get_logger(__name__)


# Simple data class to store paper information
class PaperInfo:
    def __init__(self, id, title, github_link, paper_link, code_link, stars):
        self.id = id
        self.title = title
        self.github_link = github_link
        self.paper_link = paper_link
        self.code_link = code_link
        self.stars = stars


def setup_database():
    """Set up and return a database session"""
    engine = create_engine("sqlite:///papers.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def fetch_latest_papers(limit=100):
    """Fetch latest papers and save to database"""
    logger.info("Starting to fetch latest papers...")
    base_url = "https://paperswithcode.com/latest"
    papers = scrape_papers_with_pagination(base_url, target_count=limit)

    session = setup_database()
    try:
        new_count, updated_count = save_papers_to_db(papers, session)
        logger.info(f"New papers added: {new_count}")
        logger.info(f"Papers updated: {updated_count}")
        total_count = session.query(Paper).count()
        logger.info(f"Total papers in database: {total_count}")
    finally:
        session.close()

    return new_count + updated_count


def rank_and_select_papers(limit=3):
    """Rank papers and select the top papers, up to the specified limit"""
    logger.info("Starting paper ranking...")
    session = setup_database()
    try:
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

        top_papers = []
        logger.info("Top recommended papers:")
        # Ensure we only process valid paper IDs
        valid_ids = [pid for pid in ranked_paper_ids if isinstance(pid, int)][:limit]

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
                    stars=paper.stars
                )
                
                top_papers.append(paper_info)
                logger.info(f"{rank}. [ID: {paper.id}] {paper.title}")
                logger.info(f"   GitHub: {paper.github_link}")
                logger.info(f"   Paper: {paper.paper_link}\n")

                # Mark paper as read
                paper.thoroughly_read = True

        # Commit read markings
        session.commit()

        return top_papers
    finally:
        session.close()


def process_paper(paper_info):
    """Process a single paper: download PDF, convert to Markdown, summarize"""
    logger.info(f"Starting to process paper: {paper_info.title}")

    # Download PDF
    if paper_info.paper_link:
        logger.info(f"Downloading paper PDF: {paper_info.paper_link}")
        download_pdf(paper_info.paper_link)

        # Find most recently downloaded PDF file
        pdf_files = [f for f in os.listdir(".") if f.endswith(".pdf")]
        if pdf_files:
            # Sort by modification time, get the latest PDF
            latest_pdf = sorted(
                pdf_files, key=lambda x: os.path.getmtime(x), reverse=True
            )[0]

            # Convert to Markdown
            logger.info(f"Converting PDF to Markdown: {latest_pdf}")
            try:
                convert_to_markdown(latest_pdf)

                # Summarize paper
                logger.info("Summarizing paper content...")
                with open("result.json") as f:
                    import json

                    data = json.load(f)
                    pages_info = data["pages"]

                content = ""
                for page in pages_info:
                    content += page["md"]

                # Add paper metadata
                paper_metadata = f"""
# {paper_info.title}

## Metadata
- **GitHub**: {paper_info.github_link}
- **Paper**: {paper_info.paper_link}
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
                logger.error(f"Error during conversion or summarization: {str(e)}")
        else:
            logger.error("Downloaded PDF file not found")
    else:
        logger.error("Paper has no available PDF link")

    return None


def main():
    """Main pipeline function"""
    load_dotenv()  # Load environment variables

    # Step 1: Get latest papers
    paper_count = fetch_latest_papers(limit=100)
    
    # Step 2: Rank papers and make selection
    session = setup_database()
    try:
        # Check if there are any unread papers in the database
        unread_papers_exist = session.query(Paper).filter_by(thoroughly_read=False).first() is not None
        
        if paper_count == 0 and not unread_papers_exist:
            logger.info("No new papers and all existing papers have been read, pipeline complete")
            return
        
        if paper_count == 0:
            logger.info("No new papers, selecting most interesting paper from database")
            # When no new papers, limit to just 1 most interesting paper
            top_papers = rank_and_select_papers(limit=1)
        else:
            # Normal case: select top 3 papers
            top_papers = rank_and_select_papers(limit=3)
            
        if not top_papers:
            logger.info("No papers worth reading were selected, pipeline complete")
            return

        if paper_count == 0 and top_papers:
            logger.info(f"Selected 1 most interesting paper from database: {top_papers[0].title}")
    finally:
        session.close()

    # Step 3: Process selected papers
    summary_files = []
    for paper in top_papers:
        summary_file = process_paper(paper)
        if summary_file:
            summary_files.append(summary_file)

    # Step 4: Generate summary report
    if summary_files:
        date = datetime.now().strftime("%Y-%m-%d")
        with open(f"paper_digest_{date}.md", "w", encoding="utf-8") as report:
            report.write(f"# Paper Digest Summary - {date}\n\n")

            for summary_file in summary_files:
                try:
                    with open(summary_file, "r", encoding="utf-8") as f:
                        summary_content = f.read()

                    report.write(summary_content)
                    report.write("\n\n---\n\n")  # Separator
                except Exception as e:
                    logger.error(f"Error reading summary file: {str(e)}")

        logger.info(f"Summary report generated: paper_digest_{date}.md")
    else:
        logger.info("No paper summaries were generated, pipeline complete")


if __name__ == "__main__":
    main()
