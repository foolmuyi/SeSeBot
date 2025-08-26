import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv('Hyperbolic_API_KEY')
client = OpenAI(api_key=API_KEY, base_url="https://api.hyperbolic.xyz/v1")
def get_ai_response(user_message):
    response = client.chat.completions.create(model="deepseek-ai/DeepSeek-R1-0528", messages=user_message, stream=True, 
        temperature=0.6, top_p=0.7, max_tokens=9000)
    for chunk in response:
        if len(chunk.choices) > 0:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content