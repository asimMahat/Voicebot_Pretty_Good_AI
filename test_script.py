# from openai import OpenAI

# client = OpenAI()

# response = client.chat.completions.create(
#     model="gpt-4o-mini",
#     messages=[
#         {"role": "user", "content": " Suggest a name for my baby boy starts with A ?"}
#     ]
# )

# print(response.choices[0].message.content)

from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
print(response.usage)  # Shows tokens used
