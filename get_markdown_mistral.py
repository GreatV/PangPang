import os
from mistralai import Mistral
import dotenv
import json


dotenv.load_dotenv()

mistral_api_key = os.environ["MISTRAL_API_KEY"]


def convert_to_markdown(pdf_filename):
    client = Mistral(api_key=mistral_api_key)
    uploaded_pdf = client.files.upload(
        file={
            "file_name": pdf_filename,
            "content": open(pdf_filename, "rb"),
        },
        purpose="ocr",
    )

    signed_url = client.files.get_signed_url(file_id=uploaded_pdf.id)

    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": signed_url.url,
        },
    )

    content = json.loads(ocr_response.model_dump_json())
    with open("result.json", "w") as f:
        json.dump(content, f)


if __name__ == "__main__":
    convert_to_markdown("./data/2503.01840v1.pdf")
