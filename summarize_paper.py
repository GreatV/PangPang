from openai import OpenAI
import json
from dotenv import load_dotenv
import os
import yaml
from logger_config import get_logger
from datetime import datetime

load_dotenv()

# Get logger for the current module
logger = get_logger(__name__)


def load_config():
    """
    Load configuration from YAML file with UTF-8 encoding
    """
    with open("summarize_config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config


def summarize_paper(text):
    """
    Summarize the paper using OpenAI API
    :param text: The original paper text
    :param model: The model to use (default is gpt-4)
    :param max_tokens: Maximum number of tokens for the summary
    :return: Summarized text
    """
    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"), base_url="https://api.deepseek.com"
    )
    config = load_config()
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": config["system_message"]},
            {"role": "user", "content": text},
        ],
        temperature=config["temperature"],
    )
    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    with open("result.json") as f:
        data = json.load(f)
        pages_info = data["pages"]

        content = ""
        for page in pages_info:
            content += page["md"]
        paper_text = content

        # Call the summarize function
        summary = summarize_paper(paper_text)

        logger.info("Speed Reading Brief:")
        logger.info(summary)

        date = datetime.now().strftime("%Y-%m-%d")
        with open(f"summary_{date}.md", "w") as f:
            f.write(summary)
