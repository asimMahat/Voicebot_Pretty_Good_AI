import openai

def test_openai_key():
    # 1. Get the API key from the user
    api_key = input("Enter your OpenAI API key: ").strip()
    
    # 2. Initialize the client
    client = openai.OpenAI(api_key=api_key)
    
    # 3. Ask a test question
    user_prompt = input("What would you like to ask the AI? ")

    try:
        print("\nConnecting to OpenAI...")
        # 4. Attempt a simple chat completion
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant confirming the API works."},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=50
        )
        
        # 5. Display the result
        print("-" * 30)
        print("Success! Here is the response:")
        print(response.choices[0].message.content)
        print("-" * 30)

    except openai.AuthenticationError:
        print("Error: The API key is invalid or incorrect.")
    except openai.RateLimitError:
        print("Error: You have hit your rate limit or run out of credits.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    test_openai_key()