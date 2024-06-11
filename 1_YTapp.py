import os
from openai import OpenAI
from dotenv import load_dotenv, set_key
load_dotenv()

key = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=key)

description = """You are a Investor Analyst Bot. You will be given a
company's pitch deck that you need to analyze. You need to first understand all the text and images in the document.
Your task is then to act as a chatbot where a user will ask questions on the company and you must give a detailed answer to the user."""

instructions = """If the question that is asked is outside the knowledge base that is provided. If that information isn't in the Pitch Deck provided
then go search the web or use your own knowledge to answer the question. The answer must be in detail and must be the latest information."""

assistant = client.beta.assistants.create(
    name="Pitch Deck Analysis Bot",
    description=description,
    instructions=instructions,
    model="gpt-4o",
    tools=[{"type":"file_search"}]
    )

print(assistant)
set_key('.env', 'ASSISTANT_ID', assistant.id)