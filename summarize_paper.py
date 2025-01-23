from openai import OpenAI
import json
from dotenv import load_dotenv
import os

load_dotenv()


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
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "You are a research paper analyst. Please summarize the following paper and generate a speed-reading brief in Chinese.",
            },
            {"role": "user", "content": text},
        ],
        temperature=0.7,
    )
    return response.choices[0].message.content.strip()


with open("result.json") as f:
    data = json.load(f)
    pages_info = data["pages"]

content = ""
for page in pages_info:
    content += page["md"]
paper_text = content

# Call the summarize function
summary = summarize_paper(paper_text)

print("Speed Reading Brief:")
print(summary)
