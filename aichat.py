import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# API_KEY = os.getenv('OPENAI_API_KEY')
# client = OpenAI(api_key=API_KEY)
# def get_ai_response(user_message):
#     response = client.chat.completions.create(model="gpt-4o-mini-2024-07-18", messages=user_message)
#     return response.choices[0].message.content


API_KEY = os.getenv('Hyperbolic_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.hyperbolic.xyz/v1")
def get_ai_response(user_message):
    response = client.chat.completions.create(model="deepseek-ai/DeepSeek-R1", messages=user_message, temperature=0.8, max_tokens=6000)
    return response.choices[0].message.content
