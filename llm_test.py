øimport ollama

def ask_llm(prompt: str):
    resp = ollama.chat(
        model="llama3.1",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
    )
    return resp["message"]["content"]

if __name__ == "__main__":
    print(ask_llm("Say hello in one sentence."))

