# Generate a string longer than 32 characters to trigger the buffer overflow
content = "A" * 40

# Save the content to a file for input to the program
with open("input.txt", "w") as f:
    f.write(content)